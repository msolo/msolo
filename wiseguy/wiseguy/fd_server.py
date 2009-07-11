"""A tiny server to dole out file descriptors to the requesting process."""

import errno
import logging
import _multiprocessing
import os
import socket
import SocketServer
import time

from wiseguy import embedded_sock_server


class FdClientError(embedded_sock_server.ClientError):
  pass


class FdClient(embedded_sock_server.SocketClient):
  def get_fd_for_address(self, bind_address):
    self.send_str('REQ_FD')
    self.send_str(bind_string(bind_address))
    response = self.recv_str()
    if response == 'OK':
      return _multiprocessing.recvfd(self.socket.fileno())
    elif response == 'ERROR':
      raise FdClientError(self.recv_str())
    else:
      raise FdClientError('bad response: %r' % response)

  def get_pid(self):
    self.send_str('REQ_PID')
    response = self.recv_str()
    if response == 'OK':
      return self.recv_int()
    raise FdClientError('bad response: %r' % response)


class FdRequestHandler(embedded_sock_server.EmbeddedHandler):
  def handle_REQ_FD(self):
    bind_address = self.recv_str()
    if bind_address in self.server.fd_map:
      bound_fd = self.server.fd_map[bind_address]
      logging.info('request fd: %s %s', bind_address, bound_fd)
      self.send_str('OK')
      _multiprocessing.sendfd(self.request.fileno(), bound_fd)
    else:
      logging.error('request fd: %s', bind_address)
      self.send_str('ERROR')
      self.send_str('No fd matching %r' % bind_address)

  def handle_REQ_PID(self):
    self.send_str('OK')
    self.send_int(os.getpid())


class FdServer(embedded_sock_server.EmbeddedSockServer):
  """Handle requests for file descriptors.

  The basic protocol is netstring like so we can chat but periodically call
  out to do the sendfd/recvfd referencing the same socket we are listening on.

  CLIENT:
    send_str REQ_FD
    send_str (bind address)
    recv_str OK -> recvfd
             ERROR -> recv_str (error message)

  SERVER:
    accept()
    recv_str REQ_FD
             recv_str (bind address)
             send_str OK -> sendfd
                      ERROR -> send_str (error message)
  """

  # map bind args to a socket object (maybe just an fd?)
  fd_map = {}
  thread_name = 'fd_server'

  _bound = False

    
  def register_fd(self, bind_address, fd):
    self.fd_map[bind_string(bind_address)] = fd

  def server_bind(self):
    # always register yourself
    bind_address = self.server_address
    try:
      SocketServer.UnixStreamServer.server_bind(self)
      logging.info('bound fd_server %s', bind_address)
    except socket.error, e:
      if e[0] == errno.EADDRINUSE:
        logging.info('requesting bound fd %s', bind_address)
        try:
          fd_client = FdClient(self.server_address)
          fd = fd_client.get_fd_for_address(self.server_address)
          self.socket = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
        except socket.error, e:
          logging.warning('forced teardown on %s', bind_address)
          os.remove(self.server_address)
          SocketServer.UnixStreamServer.server_bind(self)
    bound_fd = self.socket.fileno()
    self.register_fd(bind_address, bound_fd)
    logging.info('registered fd %s %s', bind_address, bound_fd)
    self._bound = True
    
  def start(self):
    if not self._bound:
      self.server_bind()
      self.server_activate()
    embedded_sock_server.EmbeddedSockServer.start(self)


def bind_string(bind_address):
  if isinstance(bind_address, basestring):
    return bind_address
  else:
    # assume it's a tuple of (ip, port)
    return '%s:%s' % bind_address


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  server = FdServer('/tmp/fd_server.sock', FdRequestHandler)
  server.start()
  time.sleep(1000)
