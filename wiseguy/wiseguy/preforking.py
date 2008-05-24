import errno
import logging
import os
import os.path
import signal
import socket
import subprocess
import time
import sys

import cPickle as pickle

import manager

log = logging.getLogger('wsgi')

# a class to handle a managed set of processes serving FastCGI requests
class PreForkingMixIn(object):
    signal_list = (signal.SIGTERM, signal.SIGINT, signal.SIGALRM,
                   signal.SIGHUP)
    alarm_interval = 1
    
    def parent_signal_handler(self, signalnum, stack_frame):
        if signalnum != signal.SIGALRM:
            log.debug("parent signal: %s", signalnum)

        if signalnum in (signal.SIGTERM, signal.SIGINT):
            self._quit = True
            # send a SIGKILL so kill/^C can stop a server no matter
            # what the child is doing
            signalnum = signal.SIGKILL
        elif signalnum == signal.SIGHUP:
            # we change a SIGHUP to a SIGTERM for the children since the HUP
            # seems to get blocked by some of the code called by most servlets
            signalnum = signal.SIGTERM
        elif signalnum == signal.SIGALRM:
            # set an emergency alarm for 60 seconds - just in case
            signal.alarm(60)
            # signal.alarm(self.alarm_interval)
            return
            
        # the parent repeats the signal to the children
        for pid in self._child_pids:
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
        log.debug("child signal: %s", signalnum)
        if signalnum in (signal.SIGTERM, signal.SIGINT):
            self._quit = True

    def install_child_signals(self):
        for sig in self.signal_list:
            signal.signal(sig, signal.SIG_DFL)

        signal.signal(signal.SIGTERM, self.child_signal_handler)
        signal.signal(signal.SIGINT, self.child_signal_handler)


    def manage_children(self):
        # this code looks a little fishy to me, too much sharing of data
        # between separate systems - would much prefer one mechanesm for
        # cleanly registering periodic tasks

        if self._management_address:
            management_server = manager.create_http_server(
                self._management_address,
                self, self._management_server_class)
        else:
            management_server = None

        last_rss_check = time.time()
        while len(self._child_pids):
            # we need an alarm to "wake up" and do something other than wait
            # for a child to die
            if self.alarm_interval is not None:
                signal.alarm(self.alarm_interval)
            #time.sleep(5.0)
            try:
                #pid, status = os.waitpid(-1, os.WNOHANG)
                pid, status = os.wait()

                try:
                    self._child_pids.remove(pid)
                    log.info("child finished: %s, %s", pid, status)
                except KeyError, e:
                    log.debug("child finished, no such pid: %s, %s",
                                pid, status)
                    # this is probably a secondary process that we aren't
                    # interested in - just wait for the next child to die
                    continue
                if pid and status != 0:
                    self.handle_bad_child(pid, status)
            except OSError, e:
                if e[0] == errno.EINTR:
                    log.debug("process interrupted")
                elif e[0] == errno.ECHILD:
                    log.error("no children, terminating parent: %s", e)
                    break
                else:
                    # error that aren't expected, or understood should log, but
                    # not stop the server
                    log.exception("unhandled error in manage_children")

            # limit children based on memory consumption
            # FIXME: might want to fork off this new children first, presuming
            # there are resources to do so, then kill the unruly children. this
            # might result in smoother response times
            if self._max_rss and self._allow_spawning:
                now = time.time()
                if now - last_rss_check >= 60:
                    last_rss_check = now
                    for pid in self._child_pids:
                        try:
                            rss = get_memory_usage(pid)['VmRSS']
                        except MemoryException, e:
                            log.exception('error in memory supervisor')
                            continue
                        
                        if rss > self._max_rss:
                            log.info("kill child pid: %s, rss: %s", pid, rss)
                            os.kill(pid, signal.SIGTERM)

            # NOTE: the timeout socket in the server assurs we don't block too
            # long here. wish i could multiplex listen for obituaries and
            # incoming connections with the same mechanesm
            if management_server:
                management_server.handle_request()

            while (not self._quit and
                   len(self._child_pids) < self._workers):
                if not self._allow_spawning:
                    log.warning("spawning disabled")
                    break
                self.spawn_child()

    # spawn another n children and kill off the old ones so the code cleanly
    # restarts
    # workers - new number of worker processes
    def handle_server_cycle(self, skew=0, workers=None, force=False):
        if workers is not None and not 1 <= workers <= 64:
            raise ValueError('unsane worker count: %s', workers)
        
        self.set_allow_spawning(True)
        old_pids = tuple(self._child_pids)
        if workers:
            self._workers = workers
            
        for i, pid in enumerate(old_pids):
            if not workers or i < workers:
                self.spawn_child()
            if force:
                os.kill(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGTERM)
            if skew:
                time.sleep(skew)
                
        while len(self._child_pids) < workers:
            self.spawn_child()
            
    def handle_bad_child(self, pid, status):
        # a child exitted with a non-zero return code
        log.error("child error on exit: %s, %s", pid, status)

    def handle_server_profile(
        self, profile_path, profile_uri, request_count, skip_request_count,
        bias, profiler_module):
        try:
            pid = tuple(self._child_pids)[0]
            self.spawn_child(profile_path, profile_uri, request_count, skip_request_count,
                             bias, profiler_module)
            os.kill(pid, signal.SIGTERM)
        except:
            log.exception("handle_server_profile")

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
            log.exception("handle_server_last_profile_data")
            return (500, str(e))

    def error(self, req, exception):
        return super(PreForkingMixIn, self).error(req, exception)
    
    def spawn_child(self, profile_path=None, profile_uri=None,
                    max_requests=None, skip_profile_requests=None,
                    profile_bias=None, profiler_module=None):
        if not self._allow_spawning:
            log.warning('spawn_child is disabled')
            return
        
        log.debug("respawning a child")
        pid = os.fork()
        if not pid:
            # child
            self._parent = False
            self.install_child_signals()

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
                        log.exception("error removing symlink: %s",
                                      last_profile_link)
                self._profile = get_profiler(profiler_module, path,
                                             bias=profile_bias)

            if profile_uri:
                import re
                self._profile_uri_regex = re.compile(profile_uri)

            # this was a premature optimization to toggle in and out of profile
            # mode only if you were actually profiling a specific servlet
            # pattern - it seems better to just wrap this in the
            # _should_profile_request function
            #if self._profile and not self._profile_uri_regex:
            #    self._profile.runcall(self._child_request_loop)
            #else:
            self._child_request_loop()

            if self._profile:
                self._profile.close()
                last_profile_link = os.path.join(
                    os.path.dirname(self._profile.filename),
                    last_profile_symlink_name)
                os.symlink(self._profile.filename, last_profile_link)

            # note: os._exit skips atexit handlers and doesn't flush stdio
            # buffers. atexit might reasonably be required by an application,
            # so i'm making calling sys.exit() instead. this seems in line
            # with other wsgi servers.
            #
            # ok, so the problem is that sys.exit() closes other file
            # descriptors that may have been inherited after the initial fork,
            # for instance the embedded managment server
            #sys.exit(0)
            os._exit(0)
        else:
            # parent
            self._child_pids.add(pid)
            return pid
        
    def serve_forever(self):
        while len(self._child_pids) < self._workers:
            self.spawn_child()

        self.install_parent_signals()
        try:
            self.manage_children()
        except:
            log.exception("unhandled exception in manage_children, exitting")

class MemoryException(Exception):
    pass

def generic_get_memory_usage(pid):
    """
    get memory usage (rss) of a child by executing ps - this is pretty ghetto
    i cannot find a programmatic api that does this correctly on both bsd and
    linux platforms - there are long discussions on Python mailing lists about
    this with no apparently resolution.

    this is especially nasty since the Mac OS X version of this only provides
    the ability to look at 1 process at a time, and only show RSS and VSS.
    arguably, these are the most useful anyway
    """
    cmd = ['ps', '-orss,vsz', '-p', str(pid)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, close_fds=True)
        # if you don't wait, you leak file descriptors
        proc.wait()
    except OSError, e:
        if e[0] in (errno.EINTR,):
            raise MemoryException("interrupted during wait()")
        else:
            # log.exception("unexpected error in get_memory_usage")
            raise MemoryException("unexpected error: %s" % e)
    lines = proc.stdout.readlines()
    try:
        rss_size_kb, vsz_kb = lines[-1].strip().split()
        rss_size_kb, vsz_kb = int(rss_size_kb), int(vsz_kb)
    except ValueError:
        # log.exception("bad value for process RSS:\n%s", str(lines))
        raise MemoryException("bad value: %s" % str(lines))

    return {'VmRSS':rss_size_kb, 'VmSize':vsz_kb}

# guarantee that at least VmRSS and VmSize are in the mem_stats
vm_keys = ('VmRSS', 'VmSize') #, 'VmData', 'VmPeak')
def linux_get_memory_usage(pid):
    """
    return dict of memory usage numbers from the procfs entry
    """
    
    try:
        path = '/proc/%s/status' % pid
        mem_stats = {}
        f = open(path)
        for line in f:
            if line.startswith('Vm'):
                key, value = line.strip().split(':')
                mem_stats[key] = int(value.split()[0].strip())
        f.close()
        for key in vm_keys:
            if key not in mem_stats:
                raise MemoryException('missing key: %s' % key)
        return mem_stats
    except Exception, e:
        raise MemoryException("unexpected error: %s" % e)

    
if sys.platform == 'linux2':
    get_memory_usage = linux_get_memory_usage
else:
    get_memory_usage = generic_get_memory_usage

last_profile_symlink_name = 'last_profile'

# make hotshot/profile/cProfile work the same way by selectively wrapping
# certain classes with a proxy
def get_profiler(profiler_module, path, bias=None):
    if profiler_module == 'hotshot':
        import hotshot
        prof = hotshot.Profile(path)
        setattr(prof, 'filename', path)
        return prof
    elif profiler_module == 'profile':
        import profile
        prof = profile.Profile(bias=bias)
    elif profiler_module == 'cProfile':
        import cProfile
        prof = cProfile.Profile()
    return ProfileProxy(path, prof)

class ProfileProxy(object):
    def __init__(self, filename, profile):
        self.filename = filename
        self.profile = profile

    def runcall(self, *pargs, **kargs):
        return self.profile.runcall(*pargs, **kargs)

    def close(self):
        self.profile.dump_stats(self.filename)
