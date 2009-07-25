import errno
import logging
import socket

from wsgiref import handlers
from wsgiref import simple_server

import wiseguy
try:
  from wiseguy import fd_server
except ImportError:
  # fd_server is python2.6 only
  fd_server = None
from wiseguy import managed_server
from wiseguy import preforking


class HTTPServer(simple_server.WSGIServer, managed_server.ManagedServer):
  def __init__(self, *pargs, **kargs):
    # don't bind and activate yet, that will be handled when the other class
    # initializes
    kargs['bind_and_activate'] = False
    managed_server.ManagedServer.__init__(self, *pargs, **kargs)
    RequestHandlerClass = kargs.get(
      'RequestHandlerClass', WiseguyRequestHandler)
    simple_server.WSGIServer.__init__(
      self, self._server_address, RequestHandlerClass);

  def server_bind(self):
    logging.error('server_bind')
    bind_address = self.server_address
    try:
      simple_server.WSGIServer.server_bind(self)
      self._listen_socket = self.socket
    except socket.error, e:
      if e[0] == errno.EADDRINUSE:
        fd_client = fd_server.FdClient(self._fd_server.server_address)
        fd = fd_client.get_fd_for_address(self.server_address)
        self._previous_pid = fd_client.get_pid()
        # reassign the socket for the SocketServer
        # fixme: does it make more sense to do this as a rebindable socket
        # rather than at the server level?
        self.socket = self._listen_socket = socket.fromfd(
          fd, socket.AF_INET, socket.SOCK_STREAM)
        # manually call bits of the base http handler:
        host, port = self.socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port
        # manually call setup_environ() since the base class implementation
        # bailed out when we could bind initially
        self.setup_environ()
      else:
        raise
    if self._fd_server:
      bound_fd = self._listen_socket.fileno()
      self._fd_server.register_fd(bind_address, bound_fd)
      logging.info('registered fd %s %s', bind_address, bound_fd)

  def server_activate(self):
    simple_server.WSGIServer.server_activate(self)
    managed_server.ManagedServer.server_activate(self)
    
  def close_request(self, request):
    simple_server.WSGIServer.close_request(self, request)
    managed_server.ManagedServer.close_request(self, request)
    

class WiseguyWSGIHandler(simple_server.ServerHandler):
  """This class controls the dispatch to the WSGI application itself.

  It's *very* confusing, but this class actually controls the logging
  for dynamic requests in the close method."""
  server_software = 'wiseguy/%s' % wiseguy.__version__

  @property
  def http_version(self):
    return self.request_handler.http_version


class WiseguyRequestHandler(simple_server.WSGIRequestHandler):
  # force http 1.1 protocol version
  protocol_version = 'HTTP/1.1'

  @property
  def http_version(self):
    return self.request_version.split('/')[-1]
  
  def log_message(self, format, *args):
    pass

  def address_string(self):
    # don't bother doing DNS resolution
    return self.client_address[0]

  def handle(self):
    # override handle() so we deal with keep-alive connections.
    # fixme: is this a bug in simple_server.WSGIRequestHandler??
    self.handle_one_request()
    while not self.close_connection:
      self.handle_one_request()

  def handle_one_request(self):
    self.raw_requestline = self.rfile.readline()
    if not self.parse_request(): # An error code has been sent, just exit
      return

    if self.server._should_profile_request(self):
      profiling = True
      self.server._profile.runcall(self._run_wsgi_app)
    else:
      self._run_wsgi_app()

  def _run_wsgi_app(self):
    handler = WiseguyWSGIHandler(
      self.rfile, self.wfile, self.get_stderr(), self.get_environ())
    handler.request_handler = self    # backpointer for logging
    handler.run(self.server.get_app())


class PreForkingHTTPWSGIServer(preforking.PreForkingMixIn, HTTPServer):
  def __init__(self, app, *pargs, **kargs):
    HTTPServer.__init__(self, *pargs, **kargs)
    self.set_app(app)
  
