# the idea is to listen on a socket and accept commands
# that can affect the child processes - mostly killing existing or spawning
# new ones. this is not a general purpose back door to modify values inside
# child processes

import errno
import logging
import socket

from wiseguy import embedded_http_server
try:
  from wiseguy import fd_server
except ImportError:
  # fd_server is python2.6 only
  fd_server = None

log = logging.getLogger('wsgi.mgmt_server')


class ManagementServer(embedded_http_server.EmbeddedHTTPServer):
  def __init__(self, server_address, RequestHandlerClass, fcgi_server):
    self.fcgi_server = fcgi_server
    embedded_http_server.EmbeddedHTTPServer.__init__(
      self, server_address, RequestHandlerClass)

  @property
  def fd_server(self):
    return self.fcgi_server._fd_server
    
  def server_bind(self):
    bind_address = self.server_address
    try:
      embedded_http_server.EmbeddedHTTPServer.server_bind(self)
    except socket.error, e:
      if e[0] == errno.EADDRINUSE and self.fd_server:
        log.info('requesting bound fd %s', self.server_address)
        fd_client = fd_server.FdClient(self.fd_server.server_address)
        fd = fd_client.get_fd_for_address(self.server_address)
        self.socket = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
      else:
        raise
    if self.fd_server:
      bound_fd = self.socket.fileno()
      self.fd_server.register_fd(bind_address, bound_fd)
      logging.info('registered fd %s %s', bind_address, bound_fd)

  
class ManagementRequestHandler(embedded_http_server.EmbeddedRequestHandler):
  path_map = embedded_http_server.EmbeddedRequestHandler.path_map.copy()
  path_map.update({
    '/server-cycle': 'handle_server_cycle',
    '/server-profile': 'handle_server_profile',
    '/server-profile-data': 'handle_server_last_profile_data',
    '/server-profile-memory': 'handle_profile_memory',
    '/server-suspend-spawning': 'handle_suspend_spawning',
    '/server-resume-spawning': 'handle_resume_spawning',
    '/server-set-max-rss': 'handle_set_max_rss',
    })
  
  def handle_set_max_rss(self):
    max_rss = self._get_int('max_rss', 0)
    try:
      self.server.fcgi_server.set_max_rss(max_rss)
      return 'OK.\n'
    except ValueError, e:
      log.warning('ignored bizzare max_rss: %s', max_rss)
      return 'ERROR.\n%s\n' % e

  def handle_resume_spawning(self):
    self.server.fcgi_server.set_allow_spawning(True)
    return 'OK.\n'

  def handle_suspend_spawning(self):
    self.server.fcgi_server.set_allow_spawning(False)
    return 'OK.\n'

  def handle_server_cycle(self):
    skew = self._get_int('skew', 0)
    workers = self._get_int('workers', None)
    force = self._get_int('force', False)
    self.server.fcgi_server.handle_server_cycle(skew, workers, force)
    return 'cycled.\n'
    
  def handle_server_profile(self):
    profile_path = self._get_str('profile_path', '/tmp')
    profile_uri = self._get_str('profile_uri', None)
    profiler_module = self._get_str('profiler_module', 'cProfile')
    request_count = self._get_int('request_count', 1000)
    skip_request_count = self._get_int('skip_request_count', 0)
    bias = self._get_float('bias', None)

    self.server.fcgi_server.handle_server_profile(
      profile_path, profile_uri, request_count, skip_request_count,
      bias, profiler_module)
    return ('starting profiler: %s (bias: %s).\n' %
            (profiler_module, bias))

  def handle_server_last_profile_data(self):
    profile_path = self._get_str('profile_path', '/tmp')
    
    self.response_code, data = self.server.fcgi_server.handle_server_last_profile_data(
      profile_path)
    if self.response_code == 200:
      self.content_type = 'application/octet-stream'
    return data

  # note: this sets a variable in the parent - now you need
  # to cycle the children to actually collect data
  def handle_profile_memory(self):
    enable = self._get_int('enable', 0)
    min_delta = self._get_int('min_delta', 0)
    self.server.fcgi_server.set_profile_memory(enable, min_delta)
    self.server.fcgi_server.handle_server_cycle()
    if enable:
      return 'set memory profiler: on.\n'
    else:
      return 'set memory profiler: off.\n'
