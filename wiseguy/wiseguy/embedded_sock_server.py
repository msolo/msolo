"""A tiny unix socket server to aid in controlling a particular instance.

This runs in a background thread and can process very small requests. It uses
a binary protocol at the moment, but that might be annoying for debugging in
the longer term.
"""

import errno
import logging
import os
import select
import socket
import SocketServer
import struct
import threading

INT_FORMAT = '!I'
INT_SIZE = struct.calcsize(INT_FORMAT)


class ClientError(Exception):
  pass


def disconnect_on_timeout(method):
  def _socket_wrapper(self, *args):
    try:
      return method(self, *args)
    except socket.timeout:
      self.disconnect()
      raise
    except (IOError, OSError):
      self.disconnect()
      raise
  return _socket_wrapper


def disconnect_on_completion(method):
  def _socket_wrapper(self, *args):
    try:
      return method(self, *args)
    finally:
      self.disconnect()
  return _socket_wrapper


class _SocketChatter(object):
  @disconnect_on_timeout
  def send_int(self, i):
    self.socket.sendall(struct.pack(INT_FORMAT, i))

  @disconnect_on_timeout
  def recv_int(self):
    return int(struct.unpack(INT_FORMAT, self.socket.recv(INT_SIZE))[0])

  @disconnect_on_timeout
  def send_str(self, s):
    self.send_int(len(s))
    try:
      self.socket.sendall(s)
    except TypeError, e:
      logging.exception('send_str: %r', s)
      raise

  @disconnect_on_timeout
  def recv_str(self):
    strlen = self.recv_int()
    return self.socket.recv(strlen)
    

class SocketClient(_SocketChatter):
  def __init__(self, address, timeout=30.0):
    self._socket = None
    self.socket_address = address
    self.timeout = timeout

  @property
  def socket(self):
    if self._socket is None:
      self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      self._socket.settimeout(self.timeout)
      try:
        self._socket.connect(self.socket_address)
      except socket.error, e:
        logging.warning('connect %s failed: %s', self.socket_address, e)
        raise
    return self._socket

  def disconnect(self):
    self._socket = None


class EmbeddedHandler(SocketServer.BaseRequestHandler, _SocketChatter):
  @property
  def socket(self):
    # set a very large timeout - you don't want a busy server to yield too
    # many spurious timeouts, but you don't want it to hang forever either
    self.request.settimeout(30.0)
    return self.request

  def get_cmd(self):
    try:
      return self.recv_str()
    except struct.error, e:
      # usually this means we failed to read net string because the client
      # closed the connection
      return None

  def disconnect(self):
    # this implements a fake disconnect to emulate the interface used
    # by the socket chatter decorators. there is probably be a better way.
    pass
  
  def handle(self):
    # NOTE: sticking to request per connection, the keep-alive code is error
    # prone and doesn't really add value here.
    cmd = self.get_cmd()
    getattr(self, 'handle_%s' % cmd)()


class EmbeddedSockServer(SocketServer.UnixStreamServer):
  thread_name = 'embedded_sock_server'
  thread = None
  unbind_on_shutdown = True
  teardown_timeout = 2.0
  _bound = False
  _activated = False

  def __str__(self):
    return '<%s@%s>' % (self.__class__.__name__, self.server_address)
  
  def start(self):
    if not self._bound:
      self.server_bind()
    if not self._activated:
      self.server_activate()
    self.thread = threading.Thread(
      target=self.serve_forever, name=self.thread_name)
    self.thread.setDaemon(True)
    self.thread.start()

  def get_request(self):
    # Running under Linux the select() call can return, even when there isn't
    # data, so accept() will hang anyway. This of course blows, so do this
    # as non-blocking temporarily and restor whatever mischief was there to
    # begin with. Beginning to wonder if the only reasonable way to do a python
    # web server is with the dreaded asynchat.
    old_timeout = self.socket.gettimeout()
    try:
      self.socket.settimeout(0.0)
      return SocketServer.UnixStreamServer.get_request(self)
    finally:
      self.socket.settimeout(old_timeout)

  def stop(self):
    self.shutdown()
    self.thread.join(self.teardown_timeout)
    if self.unbind_on_shutdown:
      self.server_unbind()

  def server_bind(self):
    SocketServer.UnixStreamServer.server_bind(self)
    self._bound = True

  def server_unbind(self):
    try:
      os.remove(self.server_address)
      logging.debug('removed %s', self.server_address)
    except EnvironmentError, e:
      logging.error('error removing %s', self.server_address)

  def server_activate(self):
    SocketServer.UnixStreamServer.server_activate(self)
    self._activated = True

  def serve_forever(self, poll_interval=0.5):
    logging.info('started %s', self)
    self._BaseServer__serving = True
    self._BaseServer__is_shut_down.clear()
    while self._BaseServer__serving:
      try:
        ready_rfds, ready_wfds, error_fds = select.select(
          [self], [], [], poll_interval)
      except select.error, e:
        # a call to setuid() can cause your threads to receive an untrappable
        # signal, SIGRT_1 (at least on Linux)
        # fixme: this should probably go to the std library
        if e[0] == errno.EINTR:
          continue
        else:
          raise
      if ready_rfds:
        try:
          self._handle_request_noblock()
        except:
          logging.exception('error in _handle_request_noblock')
    self._BaseServer__is_shut_down.set()
    logging.info('shutdown %s', self)
