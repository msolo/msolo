import errno
import logging
import os
import re
import socket
import stat
import time

from fastcgi import fcgi

log = logging.getLogger('wsgi')

class FCGIException(Exception):
    pass

class FCGIServer(object):
    
    # @param server_address - a (host, port) tuple or string - if this is a
    # string, assume its the path to a Unix domain socket
    # if there is no server address, assume STDIN is a socket
    # @param accept_input_timeout - set a timeout between the accept() call
    # and the time we actually get data on an incoming socket, milliseconds 
    def __init__(self, server_address=None, management_address=None,
                 workers=5, max_requests=None,
                 max_rss=None, profile_path=None, profile_uri=None,
                 profile_memory=False, accept_input_timeout=0,
                 max_etime=None, profiler_module='hotshot', **kargs):
        if kargs:
            log.warning('passing deprecated args: %s', ', '.join(kargs.keys()))
        self._workers = workers
        self._server_address = server_address
        self._management_address = management_address
        # override in a subclass if you want to customized the management
        # server instance after the fact
        self._management_server_class = None
        self._listen_socket = None
        self._listen_fd = 0
        self._accept_input_timeout = accept_input_timeout
        self._child_pids = set()
        self._parent = True
        self._quit = False
        self._max_requests = max_requests
        self._max_rss = max_rss
        self._max_etime = max_etime
        self._mem_stats = None
        self._request_count = 0
        self._skip_profile_requests = 0
        self._profile_path = profile_path
        self._profile_uri = profile_uri
        self._profile_uri_regex = None
        self._profile_memory = profile_memory
        self._profile_memory_min_delta = 0
        self._profile = None
        self._profiler_module = profiler_module
        # should we allow the a new process to fork?
        self._allow_spawning = True
        
        if self._server_address:
            if (isinstance(self._server_address, basestring) and
                self._server_address.startswith('/')):
                socket_type = socket.AF_UNIX
            else:
                socket_type = socket.AF_INET
            s = socket.socket(socket_type, socket.SOCK_STREAM)
            if socket_type == socket.AF_INET:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(self._server_address)
            s.listen(socket.SOMAXCONN)
            self._listen_socket = s
            self._listen_fd = s.fileno()

        mode = os.fstat(self._listen_fd)[stat.ST_MODE]
        if not stat.S_ISSOCK(mode):
            raise FCGIException("no listening socket available")

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
        from wiseguy.preforking import get_memory_usage, MemoryException
        try:
            self._mem_stats = get_memory_usage(os.getpid())
        except MemoryException, e:
            log.warning('failed init_profile_memory: %s', str(e))
        
    def handle_profile_memory(self, req):
        # fixme: ugly hack to handle cyclic dependency
        from wiseguy.preforking import get_memory_usage, MemoryException
        try:
            current_mem_stats = get_memory_usage(os.getpid())
        except MemoryException, e:
            log.warning('failed handle_profile_memory: %s', str(e))
            return
        
        mem_delta = compute_memory_delta(self._mem_stats,
                                         current_mem_stats)
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
            log.info('profile_memory %s %s %s', current,
                     delta, request_uri)

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
                
            
    def _child_request_loop(self):
        if self._profile_memory:
            self.init_profile_memory()
        # 0 is 'flags' - I hate magic parameters
        req = fcgi.Request(self._listen_fd, 0, self._accept_input_timeout)
        # log.debug("listen_fd: %s", self._listen_fd)
        while not self._quit:
            try:
                req.accept()
                # fixme: this violates WSGI environ spec - i'm not sure it
                # belongs here anyway
                req.environ['wiseguy.start_time'] = time.time()
                profiling = False
                try:
                    if self._should_profile_request(req):
                        profiling = True
                        log.debug('profile: %s',
                                  req.environ.get('PATH_INFO', ''))
                        self._profile.runcall(self.handle, req)
                    else:
                        self.handle(req)
                except IOError, e:
                    handle_io_error(e)
                except Exception, e:
                    self.error(req, e)
                # req.environ['wiseguy.end_time'] = time.time()
                if self._max_requests is not None:
                    # if we are profiling a specific servlet, only count the
                    # hits to that servlet against the request limit
                    if self._profile_uri_regex:
                        if profiling:
                            self._request_count += 1
                    else:
                        self._request_count += 1
                    if self._request_count >= self._max_requests:
                        self._quit = True
            except IOError, e:
                handle_io_error(e)

            if self._profile_memory:
                self.handle_profile_memory(req)


    def error(self, req, e):
        """Override me"""
        raise NotImplementedError

    def handle(self, req):
        """Override me"""
        raise NotImplementedError

    def serve_forever(self):
        """Override me"""
        raise NotImplementedError

# _exception - exception causing this call
def handle_io_error(_exception):
    # NOTE: 'Write failed' is probably an aborted request where the
    # FastCGI client has closed the connection before we started
    # sending data. It would be nicer if this were its own subclass
    # but what can you do
    error = _exception[0]
    if error in (errno.EINTR, errno.EAGAIN, 'Write failed', 'Flush failed'):
        #log.debug("request failed: %s", _exception)
        pass
    elif error == errno.ETIMEDOUT:
        log.info('request timed out')
    else:
        # an unknown error at this point is probably not good, let the
        # exception kill this child process
        raise _exception

def compute_memory_delta(mem_stats1, mem_stats2):
    return dict([(key, value - mem_stats1.get(key, 0))
                 for key, value in mem_stats2.iteritems()])
