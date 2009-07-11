"""A tiny unix socket server to aid in controlling a particular instance.

This runs in a background thread and can process very small requests. It uses
a binary protocol at the moment, but that might be annoying for debugging in
the longer term.
"""

import logging
import os
import socket
import SocketServer
import struct
import threading


INT_FORMAT = '!I'
INT_SIZE = struct.calcsize(INT_FORMAT)


class ClientError(Exception):
  pass


class _SocketChatter(object):
  def send_int(self, i):
    self.socket.sendall(struct.pack(INT_FORMAT, i))

  def recv_int(self):
    return int(struct.unpack(INT_FORMAT, self.socket.recv(INT_SIZE))[0])

  def send_str(self, s):
    self.send_int(len(s))
    try:
      self.socket.sendall(s)
    except TypeError, e:
      logging.exception('send_str: %r', s)
      raise

  def recv_str(self):
    strlen = self.recv_int()
    return self.socket.recv(strlen)


class SocketClient(_SocketChatter):
  def __init__(self, address, timeout=1.0):
    self._socket = None
    self.socket_address = address
    self.timeout = timeout

  @property
  def socket(self):
    if self._socket is None:
      self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      self._socket.settimeout(self.timeout)
      self._socket.connect(self.socket_address)
    return self._socket


class EmbeddedHandler(SocketServer.BaseRequestHandler, _SocketChatter):
  @property
  def socket(self):
    return self.request

  def get_cmd(self):
    try:
      return self.recv_str()
    except struct.error, e:
      # usually this means we failed to read net string because the client
      # closed the connection
      return None

  # FIXME: these methods might need timeouts
  def handle(self):
    cmd = self.get_cmd()
    while cmd:
      getattr(self, 'handle_%s' % cmd)()
      cmd = self.get_cmd()


class EmbeddedSockServer(SocketServer.UnixStreamServer):
  thread_name = 'embedded_sock_server'
  thread = None
  unbind_on_shutdown = True
  
  def start(self):
    self.thread = threading.Thread(
      target=self.serve_forever, name=self.thread_name)
    self.thread.setDaemon(True)
    self.thread.start()

  def stop(self):
    self.shutdown()
    self.thread.join()
    if self.unbind_on_shutdown:
      try:
        os.remove(self.server_address)
      except EnvironmentError, e:
        logging.error('error removing %s', self.server_address)
