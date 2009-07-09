import errno
import logging
import os
import re
import socket
import stat
import time

log = logging.getLogger('wsgi')

class ManagedException(Exception):
    pass

class ManagedServer(object):
    
    # @param server_address - a (host, port) tuple or string - if this is a
    # string, assume its the path to a Unix domain socket
    # if there is no server address, assume STDIN is a socket
    # @param accept_input_timeout - set a timeout between the accept() call
    # and the time we actually get data on an incoming socket, milliseconds 
    def init_variables(self, server_address=None, management_address=None,
                 workers=5, max_requests=None,
                 max_rss=None, profile_path=None, profile_uri=None,
                 profile_memory=False, accept_input_timeout=0,
                 max_etime=None, profiler_module='hotshot', **kargs):

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
        self._init_functions = []
        self._exit_functions = []
        # should we allow the a new process to fork?
        self._allow_spawning = True
        

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
                log.exception('exception during init function')
                raise
        
    def _run_exit_functions(self):
        """run exit functions in LIFO order - mimic atexit functionality"""
        exc_info = None
        while self._exit_functions:
            func, targs, kargs = self._exit_functions.pop()
            try:
                func(*targs, **kargs)
            except SystemExit:
                log.exception('SystemExit raised during exit function')
            except:
                log.exception('exception during exit function')

    def error(self, req, e):
        """Override me"""
        raise NotImplementedError

    def handle(self, req):
        """Override me"""
        raise NotImplementedError

    def serve_forever(self):
        """Override me"""
        raise NotImplementedError



def compute_memory_delta(mem_stats1, mem_stats2):
    return dict([(key, value - mem_stats1.get(key, 0))
                 for key, value in mem_stats2.iteritems()])

def _register_function(function_list, function, pargs, kargs):
    function_spec = (function, pargs, kargs)
    if function_spec in function_list:
        raise ManagedException("can't register duplicate function: %s",
                            function_spec)
    function_list.append(function_spec)
