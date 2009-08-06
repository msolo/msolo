import errno
import logging
import select
import socket
import struct
import time

from wsgiref import simple_server

import wiseguy
try:
  from wiseguy import fd_server
except ImportError:
  # fd_server is python2.6 only
  fd_server = None
from wiseguy import managed_server
from wiseguy import preforking

NOLINGER = struct.pack('ii', 1, 0)

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
    bind_address = self.server_address
    try:
      simple_server.WSGIServer.server_bind(self)
      self._listen_socket = self.socket
      if self._drop_privileges_callback:
        self._drop_privileges_callback()
    except socket.error, e:
      if e[0] == errno.EADDRINUSE:
        if self._drop_privileges_callback:
          self._drop_privileges_callback()
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
    logging.debug('bound %s', self)

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
  start = None
  request_handler = None
  
  def log_exception(self, exc_info):
    try:
      elapsed = time.time() - self.start      
      logging.exception('wsgi error %s "%s" %s',
         elapsed, self.request_handler.raw_requestline, self.headers)
    finally:
      exc_info = None
    # force the connection to get torn down
    self.request_handler.close_connection = True

  @property
  def http_version(self):
    return self.request_handler.http_version
  
  def cleanup_headers(self):
    # NOTE: make sure you communicate to the client that you will close the
    # underlying connection
    if self.request_handler.close_connection:
      self.headers['Connection'] = 'close'

  def finish_response(self):
    self.start = time.time()
    if not self.result_is_file() or not self.sendfile():
      for data in self.result:
        if self.request_handler.command != 'HEAD':
          self.write(data)

      if self.request_handler.command == 'HEAD':
        self.write('')
      self.finish_content()
    self.close()


class SocketFileWrapper(object):
  """A simple wrapper to keep track of the bytes read.

  This is not complete and may break, but it is complete enough for our needs.
  """
  def __init__(self, _file, request_handler):
    self.file = _file
    self.request_handler = request_handler
    self._bytes_read = 0

  def __getattr__(self, name):
    return getattr(self.file, name)

  def read(self, *args):
    if not args and self.request_handler.command == 'POST':
      content_length = int(
        self.request_handler.headers.getheader('Content-Length', -1))
      if content_length < 0:
        result = self.file.read(*args)
      else:
        result = self.file.read(content_length)
    else:
      result = self.file.read(*args)
    self._bytes_read += len(result)
    return result

  def readline(self, *args):
    result = self.file.readline(*args)
    self._bytes_read += len(result)
    return result

  def socket_tell(self):
    return self._bytes_read
   

class WiseguyRequestHandler(simple_server.WSGIRequestHandler):
  # force http 1.1 protocol version
  protocol_version = 'HTTP/1.1'
  wsgi_handler_class = WiseguyWSGIHandler
  header_size = None
  request_count = 0
  start_time = None
  raw_requestline = None
  # how long will we wait after accepting a connection or processing a request
  # before we return to the accept() loop
  keepalive_timeout = 5.0

  def setup(self):
    self.connection = self.request
    # NOTE: these were added when I could not figure out where the load
    # balancer was getting confused. I'm not convinced they are necessary
    # so I'm removing them for now.
    #self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    #self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 0)
    #self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, NOLINGER)
    self.rfile = self.connection.makefile('rb', self.rbufsize)
    self.wfile = self.connection.makefile('wb', self.wbufsize)
    self.rfile = SocketFileWrapper(self.rfile, self)

  def parse_request(self):
    try:
      return simple_server.WSGIRequestHandler.parse_request(self)
    finally:
      # save the amount of data read at this point to optimize POST
      # keep-alive
      self.header_size = self.rfile.socket_tell()

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
    try:
      self.handle_one_request()
      while not self.close_connection:
        self.handle_one_request()
    except IOError, e:
      elapsed = time.time() - self.start_time
      logging.warning('%s "%s" %s %8.6f',
                      self.address_string(), self.raw_requestline, e, elapsed)
    except Exception, e:
      elapsed = time.time() - self.start_time
      logging.exception('http error %s "%s" %s %s',
         self.address_string(), self.raw_requestline, e, elapsed)

  def handle_one_request(self):
    ready_rfds, ready_wfds, ready_xfds = select.select(
      [self.rfile], [], [self.rfile], self.keepalive_timeout)
    if not ready_rfds:
      logging.debug('%s closing idle connection', self.address_string())
      self.close_connection = True
      return
    self.start_time = time.time()
    try:
      self.raw_requestline = self.rfile.readline()
      if not self.parse_request(): # An error code has been sent, just exit
        return

      if self.server._should_profile_request(self):
        profiling = True
        self.server._profile.runcall(self._run_wsgi_app)
      else:
        self._run_wsgi_app()

      # This deserves some explanation. If we get a malformed request, bail
      # out early or for any other reason don't consume the inbound stream,
      # we need to close the connection to prevent a persistent connection
      # from getting confused. The best way to handle this is to assume we
      # close on a POST and only keep alive when we are pretty sure we can.
      # This check means that only urlencoded POSTs are going to stay alive,
      # multipart forms with close every time.
      if self.command == 'POST':
        self.close_connection = True
        content_length_value = self.headers.getheader('Content-Length')
        if content_length_value is not None:
          content_length = int(content_length_value)
          # We consider the POST request 'safe' to keep alive when we know the
          # size before hand and that matches exactly the amount of data we
          # have read from the inbound stream.
          if self.rfile.socket_tell() == (self.header_size + content_length):
            self.close_connection = False
    finally:
      self.request_count += 1

  def _run_wsgi_app(self):
    handler = self.wsgi_handler_class(
      self.rfile, self.wfile, self.get_stderr(), self.get_environ())
    # NOTE: handy backpointer, but gc problem?
    handler.request_handler = self
    handler.run(self.server.get_app())
    handler.request_handler = None

class PreForkingHTTPWSGIServer(preforking.PreForkingMixIn, HTTPServer):
  def __init__(self, app, *pargs, **kargs):
    HTTPServer.__init__(self, *pargs, **kargs)
    self.set_app(app)
