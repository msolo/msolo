import errno
import fcntl
import logging
import os
import signal
import socket
import sys
import threading

try:
  from wiseguy import fd_server
except ImportError:
  # fd_server is python2.6 only
  fd_server = None
  
from wiseguy import management_server
from wiseguy import micro_management_server


class WiseguyError(Exception):
  pass


class ManagedServer(object):
  management_server_class = management_server.ManagementServer
  
  def __init__(self, server_address=None, management_address=None,
               workers=5, max_requests=None,
               max_rss=None, profile_path=None, profile_uri=None,
               profile_memory=False, accept_input_timeout=0,
               profiler_module='cProfile',
               bind_and_activate=True,
               fd_server_address=None,
               drop_privileges_callback=None,
               **kargs):
    """Construct the manager for a particular server instance.
    server_address - a (host, port) tuple or string
      if this is a string, assume its the path to a Unix domain socket
      if there is no server address, assume STDIN is a socket
    accept_input_timeout - set a timeout between the accept() call
      and the time we get data on an incoming socket, milliseconds 
    """
    if kargs:
      logging.warning('passing deprecated args: %s', ', '.join(kargs.keys()))
      
    self._workers = workers
    self._server_address = server_address
    self._management_address = management_address
    self._fd_server_address = fd_server_address
    self._listen_socket = None
    self._listen_fd = 0
    self._accept_input_timeout = accept_input_timeout
    self._child_pids = set()
    self._quit = False
    self._max_requests = max_requests
    self._max_rss = max_rss
    self._mem_stats = None
    self._request_count = 0
    self._skip_profile_requests = 0
    self._profile_path = profile_path
    self._profile_uri = profile_uri
    self._profile_uri_regex = None
    self._profile_memory = profile_memory
    self._profile_memory_min_delta = 0
    self._profile = None
    self._profiling = None
    self._profiler_module = profiler_module
    self._init_functions = []
    self._exit_functions = []
    # FIXME: should we add a _privileged_functions? this would run before
    # we drop down from root. would we run these if you weren't root?
    self._drop_privileges_callback = drop_privileges_callback
    # should we allow the a new process to fork?
    self._allow_spawning = True

    self._management_server = None
    # the address of the umgmt server in the currently running managed server,
    # if there is one
    self._previous_umgmt_address = None
    # sometimes multiple threads (management servers) might need to cleanly
    # modify the internal state of the running server.
    self._lock = threading.RLock()
    self._fd_server_lock_fd = None

    if fd_server and self._fd_server_address:
      # create the instance, but don't start it up just yet
      # you don't want to start listening until everything else is up and
      # running, lest you have a race condition when there is a fast sequence
      # of restarts
      self._fd_server = fd_server.FdServer(
        self._fd_server_address, fd_server.FdRequestHandler,
        bind_and_activate=False)
      micro_management_server_address = '%s-%s' % (
        self._fd_server_address, os.getpid())
      self._micro_management_server = micro_management_server.MicroManagementServer(
        micro_management_server_address, self, bind_and_activate=False)
      # fixme: this feels a bit nasty - passing variables weakly behind the
      # scenes. all this code feels fragile.
      self._fd_server.micro_management_server_address = micro_management_server_address
    else:
      self._fd_server = None
      self._micro_management_server = None

    if self._management_address:
      if sys.version_info >= (2, 6):
        self._management_server = self.management_server_class(
          self._management_address, fcgi_server=self, bind_and_activate=False)
      else:
        logging.warning('unable to defer binding, upgrade to Python 2.6')
        self._management_server = self.management_server_class(
          self._management_address, fcgi_server=self)

    if bind_and_activate:
      self.server_bind()
      self.server_activate()

  def lock_startup(self):
    # we only need a lock when we are using the fd_server
    # the reason we need this is to keep multiple processes that are starting
    # up race for a connection to the existing fd_server. this is definitely
    # not the most elegant, but it should reliably keep multiple process trees
    # from setting up shop simultaneously
    if self._fd_server_address and self._fd_server_lock_fd is None:
      self._fd_server_lock_fd = os.open(self._fd_server_address + '.lock',
                                        os.O_CREAT | os.O_WRONLY)
      # use flock because it is held through a fork()
      try:
        # do a non-blocking check for the sole purpose of showing a warning
        # message to the hapless user
        fcntl.flock(self._fd_server_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      except IOError, e:
        if e[0] in (errno.EACCES, errno.EAGAIN):
          # the lock is held, dump a warning and wait
          logging.info("waiting for startup lock")
        else:
          raise
      fcntl.flock(self._fd_server_lock_fd, fcntl.LOCK_EX)
      logging.info("acquired startup lock")

  def unlock_startup(self):
    logging.info('unlock_startup')
    if self._fd_server_lock_fd is not None:
      # don't delete the lock file - it's easier to manage the locks on an
      # existing file.
      # using flock, calling unlock on any duplicate of the original fd
      # will cause the lock to be released, which is what we want.
      fcntl.flock(self._fd_server_lock_fd, fcntl.LOCK_UN)
      os.close(self._fd_server_lock_fd)
      self._fd_server_lock_fd = None

  @property
  def child_pids(self):
    """Return an immutable, consistent copy of the current child pids."""
    self._lock.acquire()
    try:
      return tuple(self._child_pids)
    finally:
      self._lock.release()

  def server_bind(self):
    raise NotImplementedError

  def server_activate(self):
    # you need to very precisely control the order of operations here so
    # that you don't end up trying to negotiate for a port from yourself.
    # you want to bind all servers first and then start their threads.
    if self._fd_server:
      self._fd_server.server_bind()
    if self._micro_management_server:
      self._micro_management_server.server_bind()
    if self._management_server:
      self._management_server.server_bind()

    # everything should now be bound, start the threads to actually listen
    if self._fd_server:
      logging.debug('start fd_server')
      self._fd_server.start()
    if self._micro_management_server:
      logging.debug('start micro_management_server')
      self._micro_management_server.start()
    if self._management_server:
      logging.debug('start management_server')
      self._management_server.start()
        
  def register_init_function(self, function, *pargs, **kargs):
    """these run in the child process prior to starting the request loop"""
    _register_function(self._init_functions, function, pargs, kargs)

  def register_exit_function(self, function, *pargs, **kargs):
    """these run in the child process, after the request loop completes"""
    _register_function(self._exit_functions, function, pargs, kargs)

  def _run_init_functions(self):
    """run functions in FIFO order, raise all exceptions"""
    for (func, targs, kargs) in self._init_functions:
      try:
        func(*targs, **kargs)
      except:
        # log in case other application logging is not yet initialized
        logging.exception('exception during init function')
        raise
    
  def _run_exit_functions(self):
    """run exit functions in LIFO order - mimic atexit functionality"""
    exc_info = None
    while self._exit_functions:
      func, targs, kargs = self._exit_functions.pop()
      try:
        func(*targs, **kargs)
      except SystemExit:
        logging.exception('SystemExit raised during exit function')
      except:
        logging.exception('exception during exit function')

  def serve_forever(self):
    """Override me"""
    raise NotImplementedError

  def init_child(self):
    """Run before entering the accept loop."""
    
    if self._profile_memory:
      self.init_profile_memory()
    self._run_init_functions()

  def handle_request(self):
    try:
      request, client_address = self.get_request()
    except socket.error:
      return
    if self.verify_request(request, client_address):
      try:
        self.process_request(request, client_address)
      except:
        self.handle_error(request, client_address)
      self.close_request(request)

  def _handle_io_error(self, _exception):
    """Reusable IOError handler.

    _exception - the exception that triggered this call
    """
    # NOTE: 'Write failed' is probably an aborted request where the
    # FastCGI client has closed the connection before we started
    # sending data. It would be nicer if this were its own subclass
    # but what can you do
    error = _exception[0]
    if error in (errno.EINTR, errno.EAGAIN, 'Write failed', 'Flush failed'):
      logging.debug("request failed: %s", _exception)
    elif error == errno.ETIMEDOUT:
      logging.info('request timed out')
    else:
      # an unknown error at this point is probably not good, let the
      # exception kill this child process
      raise _exception

  def verify_request(self, request, client_address):
    return True

  def process_request(self, request, client_address):
    self._profiling = False
    try:
      if self._should_profile_request(request):
        self._profiling = True
        logging.debug('profile: %s', request.environ.get('PATH_INFO', ''))
        self._profile.runcall(self.finish_request, request, client_address)
      else:
        self.finish_request(request, client_address)
    except IOError, e:
      self._handle_io_error(e)
    except Exception, e:
      self.handle_error(request, client_address)
      
  def get_request(self):
    """Return (request, client_address)

    Usually this performs the accept() somewhere under the hood."""
    raise NotImplementedError

  def finish_request(self, req, client_address):
    """Finish one request - usually by calling handle()."""
    self.handle(req)
    
  def exit_child(self):
    """Run after finishing the accept loop."""
    # note: os._exit skips atexit handlers and doesn't flush stdio
    # buffers. atexit might reasonably be required by an application,
    # so i'm making calling sys.exit() instead. this seems in line
    # with other wsgi servers.
    #
    # ok, so the problem is that sys.exit() closes other file
    # descriptors that may have been inherited after the initial fork,
    # for instance the embedded managment server
    #sys.exit(0)
    try:
      # emulating the atexit() functionality here - you want certain
      # thing to tear down, but others (inherited file descriptors
      # for instance) to be left intact
      self._run_exit_functions()
    finally:
      os._exit(0)

  def exit_parent(self):
    if self._micro_management_server:
      self._micro_management_server.server_unbind()

  def close_request(self, req):
    """Run after handle() returns for each connection.

    The problem is that the standard library is phrased in terms of 'requests',
    but in reality it is talking about connections."""
    if self._profile_memory:
      self.handle_profile_memory(req)
      
    if self._max_requests is not None:
      # if we are profiling a specific servlet, only count the
      # hits to that servlet against the request limit
      if self._profile_uri_regex:
        if self._profiling:
          self._request_count += 1
      else:
        self._request_count += 1
      if self._request_count >= self._max_requests:
        self._quit = True
      
    
  # The functionality below is generally about resource and process management
  # A smattering of debug functionality is there as well.

  def set_allow_spawning(self, allow):
    self._allow_spawning = allow

  # set the max_rss in KB
  def set_max_rss(self, max_rss):
    max_rss = int(max_rss)
    sane_lower_bound = 20 * 1024
    sane_upper_bound = 800 * 1024
    if sane_lower_bound <= max_rss <= sane_upper_bound:
      self._max_rss = max_rss
    else:
      raise ValueError('max_rss %s out of sane bounds' % max_rss)

  def set_profile_memory(self, profile_memory, min_delta=None):
    self._profile_memory = profile_memory
    if min_delta is not None:
      self._profile_memory_min_delta = min_delta

  def init_profile_memory(self):
    # fixme: ugly hack to handle cyclic dependency
    from wiseguy.resource_manager import get_memory_usage, MemoryException
    try:
      self._mem_stats = get_memory_usage(os.getpid())
    except MemoryException, e:
      logging.warning('failed init_profile_memory: %s', str(e))
    
  def handle_profile_memory(self, req):
    # fixme: ugly hack to handle cyclic dependency
    from wiseguy.resource_manager import get_memory_usage, MemoryException
    try:
      current_mem_stats = get_memory_usage(os.getpid())
    except MemoryException, e:
      logging.warning('failed handle_profile_memory: %s', str(e))
      return
    
    mem_delta = compute_memory_delta(self._mem_stats, current_mem_stats)
    self._mem_stats = current_mem_stats
    # only log if something changed
    if (mem_delta['VmSize'] > self._profile_memory_min_delta or
        # had to remove VMData - it's not available in generic mode
        #mem_delta['VmData'] > self._profile_memory_min_delta or
        mem_delta['VmRSS'] > self._profile_memory_min_delta):
      #path_info = req.environ.get('PATH_INFO', '')
      request_uri = req.environ.get('REQUEST_URI', '')
      delta = ('VmSize:%(VmSize)s VmData:%(VmData)s VmRSS:%(VmRSS)s'
               % mem_delta)
      current = 'CurRSS:%(VmRSS)s' % current_mem_stats
      logging.info('profile_memory %s %s %s', current, delta, request_uri)
      
  def _should_profile_request(self, req):
    # this a little fugly
    if (self._profile and
      (not self._profile_uri_regex or
       (self._profile_uri_regex and
        self._profile_uri_regex.search(
        req.environ.get('PATH_INFO', ''))))):
      if self._request_count < self._skip_profile_requests:
        return False
      return True
    return False


  # FIXME: this relies on prefork behavior
  def handle_server_profile(
    self, profile_path, profile_uri, request_count, skip_request_count,
    bias, profiler_module):
    try:
      pid = tuple(self._child_pids)[0]
      self.spawn_child(profile_path, profile_uri, request_count,
                       skip_request_count, bias, profiler_module)
      os.kill(pid, signal.SIGTERM)
    except:
      logging.exception("handle_server_profile")

  def handle_fd_server_shutdown(self):
    # this comes from the micromanagement server telling this process that the
    # new process tree is ready to take sole ownership of the fd_server socket
    if self._fd_server:
      self._fd_server.shutdown()


def compute_memory_delta(mem_stats1, mem_stats2):
  return dict([(key, value - mem_stats1.get(key, 0))
               for key, value in mem_stats2.iteritems()])


def _register_function(function_list, function, pargs, kargs):
  function_spec = (function, pargs, kargs)
  if function_spec in function_list:
    raise WiseguyError("can't register duplicate function: %s", function_spec)
  function_list.append(function_spec)
