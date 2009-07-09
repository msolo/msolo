import errno
import logging
import os
import re
import socket
import stat
import time
from wiseguy.managed_server import ManagedServer
from fastcgi import fcgi

log = logging.getLogger('wsgi')

class FCGIException(Exception):
    pass

class FCGIServer(ManagedServer):
    
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
            
        self.init_variables(server_address, management_address,
                            workers, max_requests,
                            max_rss, profile_path, profile_uri,
                            profile_memory, accept_input_timeout,
                            max_etime, profiler_module)
        
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
