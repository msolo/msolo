"""A tiny server to dole out file descriptors to the requesting process."""

import errno
import logging
import _multiprocessing
import os
import socket
import time

from wiseguy import embedded_sock_server


class FdClientError(embedded_sock_server.ClientError):
  pass


class FdClient(embedded_sock_server.SocketClient):
  @embedded_sock_server.disconnect_on_completion
  def get_available_addresses(self):
    self.send_str('REQ_ADDRS')
    response = self.recv_str()
    if response == 'OK':
      return self.recv_str()
    elif response == 'ERROR':
      raise FdClientError(self.recv_str())
    else:
      raise FdClientError('bad response: %r' % response)

  @embedded_sock_server.disconnect_on_completion
  def get_fd_for_address(self, bind_address):
    self.send_str('REQ_FD')
    self.send_str(bind_string(bind_address))
    response = self.recv_str()
    if response == 'OK':
      # NOTE: it seems fairly common to get an EGAIN on this read. the
      # underlying socket is in non-blocking mode, but i'm not sure why this
      # operation in particular seems to need a retry.
      for i in xrange(3):
        try:
          return _multiprocessing.recvfd(self.socket.fileno())
        except OSError, e:
          if e[0] == errno.EAGAIN:
            time.sleep(0.050)
          else:
            raise
      raise e
    elif response == 'ERROR':
      raise FdClientError(self.recv_str())
    else:
      raise FdClientError('bad response: %r' % response)

  @embedded_sock_server.disconnect_on_completion
  def get_pid(self):
    self.send_str('REQ_PID')
    response = self.recv_str()
    if response == 'OK':
      return self.recv_int()
    raise FdClientError('bad response: %r' % response)

  @embedded_sock_server.disconnect_on_completion
  def get_micro_management_address(self):
    self.send_str('REQ_UMGMT_ADDR')
    response = self.recv_str()
    if response == 'OK':
      return self.recv_str()
    raise FdClientError('bad response: %r' % response)

class FdRequestHandler(embedded_sock_server.EmbeddedHandler):
  def handle_REQ_FD(self):
    bind_address = self.recv_str()
    logging.info('request fd: %s', bind_address)
    if bind_address in self.server.fd_map:
      bound_fd = self.server.fd_map[bind_address]
      logging.info('sending fd: %s %s', bind_address, bound_fd)
      self.send_str('OK')
      _multiprocessing.sendfd(self.request.fileno(), bound_fd)
    else:
      logging.info('no match for requested fd: %s %s',
                    bind_address, self.server.fd_map.keys())
      self.send_str('ERROR')
      self.send_str('No fd matching %r on %s %s' % (bind_address, os.getpid(),
                    self.server.fd_map.keys()))

  def handle_REQ_PID(self):
    self.send_str('OK')
    self.send_int(os.getpid())

  def handle_REQ_UMGMT_ADDR(self):
    self.send_str('OK')
    self.send_str(self.server.micro_management_server_address)

  def handle_REQ_ADDRS(self):
    self.send_str('OK')
    self.send_str(str(self.server.fd_map.keys()))


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
  fd_map = None
  thread_name = 'fd_server'
  unbind_on_shutdown = False
  micro_management_server_address = ''
  
  def __init__(self, *pargs, **kargs):
    self.fd_map = {}
    embedded_sock_server.EmbeddedSockServer.__init__(self, *pargs, **kargs)
    
  def register_fd(self, bind_address, fd):
    self.fd_map[bind_string(bind_address)] = fd

  def handle_error(self, request, client_address):
    logging.exception('error during request from %s', client_address)

  def server_bind(self):
    # always register yourself
    bind_address = self.server_address
    try:
      embedded_sock_server.EmbeddedSockServer.server_bind(self)
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
          embedded_sock_server.EmbeddedSockServer.server_bind(self)
    bound_fd = self.socket.fileno()
    self.register_fd(bind_address, bound_fd)
    logging.info('registered fd %s %s', bind_address, bound_fd)
    logging.debug('bound %s', self)
    self._bound = True
    

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
