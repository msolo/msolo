#!/usr/bin/env python2.7

import _multiprocessing
import os
import socket
import struct
import sys

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/pyzy.sock')

env = '\n'.join(['PYZY_ENV=1', 'PWD=' + os.environ['PWD']])

def send_int(_int):
  sock.send(struct.pack('!I', _int))

def send_str(_str):
  send_int(len(_str))
  sock.send(_str)

print sys.argv

send_str(env)
send_int(len(sys.argv))
for arg in sys.argv:
  send_str(arg)
fd = sock.fileno()
_multiprocessing.sendfd(fd, sys.stdin.fileno())
_multiprocessing.sendfd(fd, sys.stdout.fileno())
_multiprocessing.sendfd(fd, sys.stderr.fileno())

return_msg_format = '!I'
pid = struct.unpack(
  return_msg_format, sock.recv(struct.calcsize(return_msg_format)))

return_msg_format = '!II'
return_code, pid = struct.unpack(
  return_msg_format, sock.recv(struct.calcsize(return_msg_format)))
print "return:", return_code, "pid:", pid
sys.exit(return_code)
