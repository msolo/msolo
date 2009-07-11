import errno
import logging
import os
import socket
import stat
import sys

from fastcgi import fcgi
try:
  from wiseguy import fd_server
except ImportError:
  # fd_server is python2.6 only
  fd_server = None
from wiseguy import managed_server


class FCGIServer(managed_server.ManagedServer):
  @property
  def server_address(self):
    return self._server_address
  
  def server_bind(self):
    if self._server_address:
      if (isinstance(self._server_address, basestring) and
          self._server_address.startswith('/')):
        socket_type = socket.AF_UNIX
      else:
        socket_type = socket.AF_INET
      try:
        self._listen_socket = socket.socket(socket_type, socket.SOCK_STREAM)
        if socket_type == socket.AF_INET:
          self._listen_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_socket.bind(self.server_address)
      except socket.error, e:
        if e[0] == errno.EADDRINUSE and self._fd_server:
          fd_client = fd_server.FdClient(self._fd_server.server_address)
          fd = fd_client.get_fd_for_address(self.server_address)
          self._previous_pid = fd_client.get_pid()
          logging.info('previous pid %s', self._previous_pid)
          self._listen_socket = socket.fromfd(
            fd, socket_type, socket.SOCK_STREAM)
        else:
          raise
      if self._fd_server:
        bound_fd = self._listen_socket.fileno()
        self._fd_server.register_fd(self._server_address, bound_fd)
        logging.info('registered fd %s %s', self.server_address, bound_fd)

  def server_activate(self):
    if self._listen_socket:
      # NOTE: does listening with too much backlog break FIFO queuing? does this mean
      # a slow worker will make some requests wait unfairly?
      self._listen_socket.listen(socket.SOMAXCONN)
      self._listen_fd = self._listen_socket.fileno()

    # for legacy reasons, we support STDIN as a valid _listen_fd
    mode = os.fstat(self._listen_fd)[stat.ST_MODE]
    if not stat.S_ISSOCK(mode):
      raise managed_server.WiseguyError("no listening socket available")

    # 0 is 'flags' - I hate magic parameters
    self._fcgi_request = fcgi.Request(
      self._listen_fd, 0, self._accept_input_timeout)
    super(FCGIServer, self).server_activate()

  def get_request(self):
    # this is a little janky, the object upon which we call accept() is actually
    # used as a request. very fun for multithreading. for now, just make it
    # look like this operates like most other python servers
    self._fcgi_request.accept()
    # fixme: client_address is always None
    return (self._fcgi_request, None)

  def handle(self, req):
    """Vaguely named, usually provided by the WSGIMix"""
    raise NotImplementedError

  def error(self, req, e):
    """Vaguely named, usually provided by the WSGIMix"""
    raise NotImplementedError

  def handle_error(self, request, client_address):
    self.error(request, sys.exc_info()[2])

  def close_request(self, req):
    """Implemented to make ManagedServer more consistent."""
    pass
  
