"""A tiny server to dole out file descriptors to the requesting process."""

import errno
import logging
import _multiprocessing
import os
import socket
import SocketServer
import struct
import threading
import time


INT_FORMAT = '!I'
INT_SIZE = struct.calcsize(INT_FORMAT)


class FdClientError(Exception):
  pass


class _FdChatter(object):
  def send_int(self, i):
    self.sock.sendall(struct.pack(INT_FORMAT, i))

  def recv_int(self):
    return int(struct.unpack(INT_FORMAT, self.sock.recv(INT_SIZE))[0])

  def send_str(self, s):
    self.send_int(len(s))
    try:
      self.sock.sendall(s)
    except TypeError, e:
      logging.exception('send_str: %r', s)
      raise

  def recv_str(self):
    strlen = self.recv_int()
    return self.sock.recv(strlen)


class FdClient(_FdChatter):
  def __init__(self, address):
    self.sock = None
    self.socket_address = address

  def get_fd_for_address(self, bind_address):
    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    self.sock.connect(self.socket_address)
    self.send_str(bind_string(bind_address))
    response = self.recv_str()
    if response == 'OK':
      return _multiprocessing.recvfd(self.sock.fileno())
    elif response == 'ERROR':
      raise FdClientError(self.recv_str())
    else:
      raise FdClientError('bad response: %r' % response)


#class FdRequestHandler(_FdChatter, SocketServer.BaseRequestHandler):
class FdRequestHandler(SocketServer.BaseRequestHandler, _FdChatter):
  @property
  def sock(self):
    return self.request
  
  # FIXME: these methods might need timeouts
  def handle(self):
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


class RebindingServer(object):
  """An abstract class specifying necessary overrides for rebinding a server.
  """
  fd_server = None

class FdServer(SocketServer.UnixStreamServer):
  """Handle requests for file descriptors.

  The basic protocol is netstring like so we can chat but periodically call
  out to do the sendfd/recvfd referencing the same socket we are listening on.

  CLIENT:
    send_str (bind address)
    recv_str OK -> recvfd
             ERROR -> recv_str (error message)

  SERVER:
    accept()
    recv_str (bind address)
    send_str OK -> sendfd
             ERROR -> send_str (error message)
  """

  # map bind args to a socket object (maybe just an fd?)
  fd_map = {}
  _thread = None
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
    self._thread = threading.Thread(
      target=self.serve_forever, name='fd_server')
    self._thread.setDaemon(True)
    self._thread.start()

  def stop(self):
    self.shutdown()
    self._thread.join()

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
