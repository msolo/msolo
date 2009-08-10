import atexit
import errno
import logging
import os.path
import random
import re
import select
import signal
import socket
import threading
import time
import sys

from wiseguy import micro_management_server
from wiseguy import resource_manager

log = logging.getLogger('wsgi')

last_profile_symlink_name = 'last_profile'

# a class to handle a managed set of processes serving FastCGI requests
class PreForkingMixIn(object):
  signal_list = (signal.SIGTERM, signal.SIGINT, signal.SIGALRM,
                 signal.SIGHUP)
  alarm_interval = None
  check_interval = 30
  rss_check_interval = 30
  
  def parent_signal_handler(self, signalnum, stack_frame):
    if signalnum != signal.SIGALRM:
      logging.debug("parent signal: %s", signalnum)

    if signalnum in (signal.SIGTERM, signal.SIGINT):
      self._quit = True
      # send a SIGKILL so kill/^C can stop a server no matter
      # what the child is doing
      signalnum = signal.SIGKILL
    elif signalnum == signal.SIGHUP:
      # we change a SIGHUP to a SIGTERM for the children since the HUP
      # seems to get blocked by some of the code called by most servlets
      signalnum = signal.SIGTERM

    # the parent repeats the signal to the children
    for pid in self.child_pids:
      # in most cases, you need to resend the signal to the child pids
      # however, this doesn't seem to be true with SIGINT, it looks like
      # there might be some python magic going on
      os.kill(pid, signalnum)

      # NOTE: the fastcgi library installs a handler to break
      # on a SIGUSR1 - hopefully this will force the other signal
      # to get handled. the fastcgi is blocked in C code, so these
      # signals can wait for a long time
      # NOTE: this doesn't seem to work too well - under reasonable load,
      # the child process just eats up CPU somewhere in a futex() loop
      #os.kill(pid, signal.SIGUSR1)

  def install_parent_signals(self):
    for sig in self.signal_list:
      signal.signal(sig, self.parent_signal_handler)

  def child_signal_handler(self, signalnum, stack_frame):
    # HUP seems to have some issues - something must be registering it
    # INT and TERM both want to cause the child to die nicely
    # if that's not what you want, you'll have to send a KILL
    logging.debug("child signal: %s", signalnum)
    if signalnum in (signal.SIGTERM, signal.SIGINT):
      self._quit = True

  def install_child_signals(self):
    for sig in self.signal_list:
      signal.signal(sig, signal.SIG_DFL)

    signal.signal(signal.SIGTERM, self.child_signal_handler)
    signal.signal(signal.SIGINT, self.child_signal_handler)

#   # NOTE: this can't be used reliably in a thread.
#   # on some platforms, you get stats about a process by exec'ing a tool and
#   # waiting for it. with multiple threads calling wait() for different
#   # processes, you get a race condition. this is on BSD for the moment.
#   def check_children_loop(self):
#     while True:
#       time.sleep(self.check_interval)
#       try:
#         self.check_children()
#       except:
#         logging.exception('check_children error')

  def check_children(self):
    # limit children based on memory consumption
    # FIXME: might want to fork off this new children first, presuming
    # there are resources to do so, then kill the unruly children. this
    # might result in smoother response times
    if not self._quit and self._max_rss and self._allow_spawning:
      for pid in self.child_pids:
        try:
          rss = resource_manager.get_memory_usage(pid)['VmRSS']
        except resource_manager.MemoryException, e:
          logging.warning('resource manager error pid: %s %s', pid, e)
          continue
        if rss > self._max_rss:
          logging.info('kill child pid: %s, rss: %s', pid, rss)
          os.kill(pid, signal.SIGTERM)
          # fixme: sigterm is ok for now, but we might need to escalate to a
          # sigkill at some point

  def manage_children(self):
    # NOTE: this code looks a little fishy to me, too much sharing of data
    # between separate systems - would much prefer one mechanesm for
    # cleanly registering periodic tasks. unfortunately, mixing threads and
    # subprocesses is a bit unclean with overlapping calls to wait().

    while len(self.child_pids):
      try:
        pid, status = os.waitpid(-1, os.WNOHANG)
        if pid:
          try:
            # NOTE: this is the first good place I can think of to use the
            # 'with' statement
            self._lock.acquire()
            try:
              self._child_pids.remove(pid)
            finally:
              self._lock.release()
            logging.info("child finished: %s, %s", pid, status)
          except KeyError, e:
            logging.debug("child finished, no such pid: %s, %s",
                      pid, status)
            # this is probably a secondary process that we aren't
            # interested in - just wait for the next child to die
            continue
          if pid and status != 0:
            self.handle_bad_child(pid, status)
      except OSError, e:
        if e[0] == errno.EINTR:
          logging.debug("process interrupted")
        elif e[0] == errno.ECHILD:
          logging.error("no children, terminating parent: %s", e)
          break
        else:
          # error that aren't expected, or understood should log, but
          # not stop the server
          logging.exception("unhandled error in manage_children")

      # if would be better to run this in it's own execution thread
      # but there are issues with too many execution paths using waitpid()
      # if something died, respawn - there will be plenty of time to scan for
      # misbehaving children later
      if not pid:
        time.sleep(self.check_interval)
        self.check_children()
      
      while (not self._quit and
             len(self.child_pids) < self._workers):
        if not self._allow_spawning:
          logging.warning("spawning disabled")
          break
        self.spawn_child()

  # spawn another n children and kill off the old ones so the code cleanly
  # restarts
  # workers - new number of worker processes
  # NOTE: THREADED this executes in another thread. there are shared variables
  # that get modified, but this shouldn't cause a problem since we mostly
  # operate on a consistent copy. the server as a whole should trend towards
  # consistency.
  def handle_server_cycle(self, skew=0, workers=None, force=False):
    if workers is not None and not 1 <= workers <= 64:
      raise ValueError('unsane worker count: %s', workers)

    self.set_allow_spawning(True)
    old_pids = self.child_pids
    if workers:
      self._lock.acquire()
      try:
        self._workers = workers
      finally:
        self._lock.release()

    for i, pid in enumerate(old_pids):
      # this is no longer helpful since it runs in a thread.
      # the main child manager will handle the creating just fine.
      #if not workers or i < workers:
      #  self.spawn_child()
      if force:
        os.kill(pid, signal.SIGKILL)
      else:
        os.kill(pid, signal.SIGTERM)
      if skew:
        time.sleep(skew)

  # NOTE: THREADED this executes in another thread. there are shared variables
  # that get modified, but this shouldn't cause a problem since we mostly
  # operate on a consistent copy. the server as a whole should trend towards
  # consistency.
  def handle_server_prune_worker(self):
    pid = None
    self._lock.acquire()
    try:
      if self._workers:
        self._workers -= 1
        pid = self.child_pids[0]
    finally:
      self._lock.release()
    if pid is not None:
      os.kill(pid, signal.SIGTERM)

  # NOTE: THREADED this executes in another thread. there are shared variables
  # that get modified, but this shouldn't cause a problem since we mostly
  # operate on a consistent copy. the server as a whole should trend towards
  # consistency.
  def handle_server_graceful_shutdown(self):
    """Keep removing workers until there aren't any.

    Each worker should terminate gracefully, as should the parent."""
    self.graceful_shutdown()

    timer = threading.Timer(5.0, self.graceful_shutdown)
    timer.setDaemon(True)
    timer.start()

    # schedule some insurance - if this thread is still alive in 30 seconds,
    # send SIGKILL to the children and let the parent tear down nicely.
    timer = threading.Timer(30.0, self.force_shutdown)
    timer.setDaemon(True)
    timer.start()

  def graceful_shutdown(self):
    for pid in self.child_pids:
      os.kill(pid, signal.SIGTERM)

  def force_shutdown(self):
    for pid in self.child_pids:
      os.kill(pid, signal.SIGKILL)

  # FIXME: this is kind of dopey the way we have to send back an http-like
  # response. should this be only in the management_server?
  def handle_server_last_profile_data(self, profile_path):
    last_profile_link = os.path.join(os.path.abspath(profile_path),
                                     last_profile_symlink_name)
    try:
      f = open(last_profile_link, 'r', 4 * 1024 * 1024)
      data = f.read()
      f.close()
      return (200, data)
    except IOError, e:
      if e[0] in (errno.ENOENT,):
        return (404, str(e))
      else:
        return (500, str(e))
    except Exception, e:
      logging.exception("handle_server_last_profile_data")
      return (500, str(e))

  def handle_bad_child(self, pid, status):
    # a child exitted with a non-zero return code
    logging.error("child error on exit: %s, %s", pid, status)

  def spawn_child(self, profile_path=None, profile_uri=None,
                  max_requests=None, skip_profile_requests=None,
                  profile_bias=None, profiler_module=None):
    if not self._allow_spawning:
      logging.warning('spawn_child is disabled')
      return

    logging.debug("respawning a child")
    pid = os.fork()
    if pid:
      # parent
      self._child_pids.add(pid)
      return pid

    # child
    self.post_fork_init()

    if not profile_path:
      profile_path = self._profile_path
    if not profile_uri:
      profile_uri = self._profile_uri
    if max_requests:
      self._max_requests = max_requests
    if skip_profile_requests:
      self._skip_profile_requests = skip_profile_requests
      # you have to increase the max number of requests to account
      # for the ones that will be skipped during warmup
      if self._max_requests is not None:
        self._max_requests += skip_profile_requests

    if profile_path:
      if profiler_module is None:
        profiler_module = self._profiler_module
      path = os.path.join(
        os.path.abspath(profile_path),
        '%s-%u.%s' % (os.path.basename(sys.argv[0]),
                      os.getpid(),
                      profiler_module))
      last_profile_link = os.path.join(
        os.path.abspath(profile_path),
        last_profile_symlink_name)
      try:
        os.remove(last_profile_link)
      except OSError, e:
        if e[0] not in (errno.ENOENT,):
          logging.exception("error removing symlink: %s",
                        last_profile_link)
      self._profile = resource_manager.get_profiler(profiler_module, path,
                                                    bias=profile_bias)

    if profile_uri:
      self._profile_uri_regex = re.compile(profile_uri)

    # run any initialization that must be done in the child post fork
    # do it here so we can get most of the wiseguy scaffold in place
    # prior
    self.init_child()
    self._child_request_loop()

    # fixme: move to managed_server.exit_child?
    if self._profile:
      self._profile.close()
      last_profile_link = os.path.join(
        os.path.dirname(self._profile.filename),
        last_profile_symlink_name)
      os.symlink(self._profile.filename, last_profile_link)
      
    self.exit_child()

  def post_fork_reinit(self):
    """Run anything that reinitializes the python process.

    This is a catch-all for patching modules that assume they
    are running in a single process environment and get confused
    by forking."""

    # quickly register our own signals
    self.install_child_signals()

    # remove any exit handlers - anything registered at this point is not
    # relevant. register a wiseguy-specific exit handler instead
    del atexit._exithandlers[:]
    
    # you don't want all your workers to have the same pseudo random order
    # go ahead and reseed it.
    random.seed()
    
  def _child_request_loop(self):
    while not self._quit:
      try:
        self.handle_request()
      except select.error, e:
        if e[0] == errno.EINTR:
          # squelch some noise
          pass
        else:
          raise
      except IOError, e:
        self._handle_io_error(e)

  def serve_forever(self):
    # if you are a stealing existing file descriptors and you know the previous
    # pid, fire up a client so you can gracefully prune the children as you
    # start up. the thinking is that if you start too quickly you will use up
    # too much memory or suddenly swap too many processes that need to do time
    # consuming operations like initialize connections.
    if self._fd_server and self._previous_pid:
      uclient = micro_management_server.MicroManagementClient(
        '%s-%s' % (self._fd_server.server_address, self._previous_pid))
    else:
      uclient = None

    while len(self.child_pids) < self._workers:
      logging.debug('serve_forever - spawn %s/%s',
                len(self._child_pids) + 1, self._workers)
      if uclient:
        try:
          logging.debug('sending prune_worker to old wiseguy')
          uclient.prune_worker()
        except socket.timeout:
          # if we timed out, maybe the parent is already dead
          logging.warning('uclient timed out during prune_worker')
        except Exception, e:
          logging.warning('uclient error during prune_worker: %s', e)
      self.spawn_child()

    # once you have spawned as many children as you think you need, send the
    # graceful_shutdown command to get rid of any child workers that might be
    # still hanging around. This will likely fail when you are increasing the
    # number of children since you will have called prune_worker() more times
    # than there are actual workers.
    if uclient:
      try:
        uclient.graceful_shutdown()
      except Exception, e:
        logging.warning('graceful_shutdown failed: %s', e)
      
    self.install_parent_signals()
    try:
      self.manage_children()
    except:
      logging.exception("unhandled exception in manage_children, exitting")

