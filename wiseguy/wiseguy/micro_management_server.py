"""A tiny server to aid in controlling a particular server instance (pid)."""

import logging

from wiseguy import embedded_sock_server


class MicroManagementError(embedded_sock_server.ClientError):
  pass


class MicroManagementClient(embedded_sock_server.SocketClient):
  @embedded_sock_server.disconnect_on_completion
  def fd_server_shutdown(self):
    self.send_str('fd_server_shutdown')
    response = self.recv_str()
    if response == 'OK':
      pass
    elif response == 'ERROR':
      error_str = self.recv_str()
      raise MicroManagementError(error_str)
    else:
      raise MicroManagementError('bad response %r' % response)

  @embedded_sock_server.disconnect_on_completion
  def prune_worker(self):
    self.send_str('prune_worker')
    response = self.recv_str()
    if response == 'OK':
      pass
    elif response == 'ERROR':
      error_str = self.recv_str()
      raise MicroManagementError(error_str)
    else:
      raise MicroManagementError('bad response %r' % response)

  @embedded_sock_server.disconnect_on_completion
  def graceful_shutdown(self):
    self.send_str('graceful_shutdown')
    response = self.recv_str()
    if response == 'OK':
      pass
    elif response == 'ERROR':
      error_str = self.recv_str()
      raise MicroManagementError(error_str)
    else:
      raise MicroManagementError('bad response %r' % response)


class MicroManagementHandler(embedded_sock_server.EmbeddedHandler):
  def handle_fd_server_shutdown(self):
    try:
      logging.info('handle_fd_server_shutdown')
      self.server.fcgi_server.handle_fd_server_shutdown()
      self.send_str('OK')
    except Exception, e:
      logging.exception('handle_fd_server_shutdown')
      self.send_str('ERROR')
      self.send_str(str(e))
  
  def handle_prune_worker(self):
    try:
      logging.info('handle_prune_worker')
      self.server.fcgi_server.handle_server_prune_worker()
      self.send_str('OK')
    except Exception, e:
      logging.exception('handle_prune_child')
      self.send_str('ERROR')
      self.send_str(str(e))

  def handle_graceful_shutdown(self):
    # this is tricky - you don't want to really wait until everything dies
    # you just want to queue the action and go about your business. also,
    # you might die before you are able to send out everything since this is
    # running in a daemon thread
    logging.info('handle_graceful_shutdown')
    self.send_str('OK')

    try:
      self.server.fcgi_server.handle_server_graceful_shutdown()
    except Exception, e:
      logging.exception('handle_graceful_shutdown')
      # don't send an error


class MicroManagementServer(embedded_sock_server.EmbeddedSockServer):
  """Handle removing child processes during the restart process."""
  thread_name = 'micro_management_server'
  fcgi_server = None
  
  def __init__(self, server_address, fcgi_server,
               RequestHandlerClass=MicroManagementHandler,
               **kargs):
    self.fcgi_server = fcgi_server
    embedded_sock_server.EmbeddedSockServer.__init__(
      self, server_address, RequestHandlerClass, **kargs)
