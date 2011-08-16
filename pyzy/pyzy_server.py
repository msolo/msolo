#!/usr/bin/env python2.6

import errno
import logging
import _multiprocessing
import optparse
import os
import socket
import struct
import sys
import time


socket_name = '/tmp/pyzy.sock'

class PyZySystemExit(SystemExit):
  pass

def pyzy_exit(return_code):
  raise PyZySystemExit(return_code)

class PyZyServer(object):
  sock = None

  def connect(self):
    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    self.sock.bind(socket_name)
    self.sock.listen(5)

  def recv_int(self, client_sock):
    return int(struct.unpack('!I', client_sock.recv(4))[0])

  def recv_str(self, client_sock):
    strlen = self.recv_int(client_sock)
    return client_sock.recv(strlen)
    
  def serve_forever(self):
    # keep track of scripts we have run
    script_set = set()
    while True:
      try:
        while os.waitpid(-1, os.WNOHANG)[0]:
          pass
      except OSError, e:
        if e[0] != errno.ECHILD:
          raise
      client_sock, addr = self.sock.accept()
      env = self.recv_str(client_sock)

      client_env = {}
      for line in env.split('\n'):
        line = line.strip()
        if line:
          key, value = line.split('=', 1)
        client_env[key] = value

      old_env = os.environ.copy()
      old_sys_path = sys.path[:]
      
      os.environ.update(client_env)
      argc = self.recv_int(client_sock)
      argv = [self.recv_str(client_sock) for x in range(argc)]
      script = os.path.abspath(argv[1])

      #fork = (script in script_set)
      fork = True
      script_set.add(script)

      if fork and os.fork() != 0:
        # parent process
        continue
      else:
        sys.path[0:0] = client_env.get('PYTHONPATH', '').split(':')

      print >> sys.stderr, script, 'fork', fork, client_env, argc, argv
      fd = client_sock.fileno()
      stdin_fd = _multiprocessing.recvfd(fd)
      stdout_fd = _multiprocessing.recvfd(fd)
      stderr_fd = _multiprocessing.recvfd(fd)

      sys.stdin = os.fdopen(stdin_fd, 'r')
      sys.stdout = os.fdopen(stdout_fd, 'w')
      sys.stderr = os.fdopen(stderr_fd, 'w')
      sys.argv = argv[1:]
      sys.exit = pyzy_exit

      pid = os.getpid()
      client_sock.send(struct.pack('!I', pid))
      
      return_code = 0
      try:
        try:
          execfile(argv[1])
        except PyZySystemExit, e:
          return_code = e[0]
        except Exception, e:
          print >> sys.stderr, e
          return_code = 1
        client_sock.send(struct.pack('!II', return_code, pid))
      finally:
        if fork:
          print >> sys.stderr, "exitting"
          os._exit(0)
        else:
          for key in os.environ:
            if key in old_env:
              os.environ[key] = old_env[key]
            else:
              del os.environ[key]
          sys.path[:] = old_sys_path

def main():
  try:
    logging.basicConfig()
    server = PyZyServer()
    server.connect()
    server.serve_forever()
  except KeyboardInterrupt, e:
    pass
  finally:
    os.remove(socket_name)

if __name__ == '__main__':
  main()
