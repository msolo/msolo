import logging
import socket
import SocketServer
import struct
import sys
import zlib

import cPickle as pickle

import spyglass.cidr

log = logging.getLogger('spyglass.spudp')

MSG_TYPE_SIZE = 4
MSG_HEADER_FORMAT = '!%usI' % MSG_TYPE_SIZE
MSG_HEADER_SIZE = struct.calcsize(MSG_HEADER_FORMAT)
MSG_TYPE_ERROR = 'err.'
MSG_TYPE_OK = 'ok..'

class __NoResponse(object):
  pass

MSG_NO_REPONSE = __NoResponse()

class SPUDPException(Exception):
  pass

MSG_FLAG_PICKLE = 0x0001
MSG_FLAG_ZIPPED = 0x0002
MSG_FLAG_RESPONSE = 0x0004

def pack_msg(msg_type, msg_data, msg_flags=0x0):
  if not isinstance(msg_data, str):
    msg_data = pickle.dumps(msg_data, pickle.HIGHEST_PROTOCOL)
    msg_flags |= MSG_FLAG_PICKLE
  if len(msg_data) > 1024:
    msg_data = zlib.compress(msg_data)
    msg_flags |= MSG_FLAG_ZIPPED
  return '%s%s' % (struct.pack(MSG_HEADER_FORMAT, msg_type, msg_flags),
           msg_data)

def unpack_msg(data):
  header = data[:MSG_HEADER_SIZE]
  payload = data[MSG_HEADER_SIZE:]
  msg_type, msg_flags = struct.unpack(MSG_HEADER_FORMAT, header)
  if (msg_flags & MSG_FLAG_ZIPPED):
    payload = zlib.decompress(payload)
  if (msg_flags & MSG_FLAG_PICKLE):
    payload = pickle.loads(payload)
  return msg_type, msg_flags, payload
  

class SPUDPRequestHandler(SocketServer.BaseRequestHandler):
  def send_error(self, error_message):
    self.send_data(MSG_TYPE_ERROR, error_message)
    
  def send_data(self, msg_type, msg_data=''):
    data = pack_msg(msg_type, msg_data, msg_flags=MSG_FLAG_RESPONSE)
    bytes_sent = self.server.socket.sendto(data, self.client_address)
    if bytes_sent != len(data):
      raise socket.error, "partial send"
  
  def handle(self):
    try:
      data, server_socket = self.request
      try:
        msg_type, msg_flags, msg_data = unpack_msg(data)
      except Exception, e:
        log.exception('corrupt msg')
      try:
        msg_handler_name = self.server._message_handler_map[msg_type]
        log.debug('recieved %s', msg_handler_name)
        msg_handler = getattr(self, msg_handler_name)
        try:
          response = msg_handler(msg_type, msg_data)
          if response is not None:
            self.send_data(MSG_TYPE_OK, response)
        except Exception, e:
          log.exception('handler error')
          self.send_error(str(e))
      except KeyError:
        self.send_error('no handler')
    except socket.timeout, e:
      pass
    except socket.error, e:
      if e[0] == errno.EAGAIN:
        pass
      else:
        log.error("error: %s, %s", e[0], e.__class__)


class SPUDPClient(object):
  def __init__(self, server_address, timeout=0.1):
    self._server_address = server_address
    self._timeout = timeout
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.settimeout(timeout)
    if sys.platform == 'linux2':
      self.max_packet_size = 64 * 1024
    else:
      self.max_packet_size = 8 * 1024

  def set_timeout(self, timeout):
    self.socket.settimeout(timeout)

  def _send(self, msg_type, msg_data=''):
    return self._send_recv(msg_type, msg_data, wait_for_response=False)
  
  def _send_recv(self, msg_type, msg_data='', wait_for_response=True):
    data = pack_msg(msg_type, msg_data)
    bytes_sent = self.socket.sendto(data, self._server_address)
    if bytes_sent != len(data):
      raise socket.error, "partial send"

    if wait_for_response:
      response, host_addr = self.socket.recvfrom(self.max_packet_size)
      msg_type, msg_flags, msg_data = unpack_msg(response)
      if not (msg_flags & MSG_FLAG_RESPONSE):
        raise SPUDPException('expected a response')
      if msg_type == MSG_TYPE_ERROR:
        raise SPUDPException(msg_data)
      return msg_data


class SPUDPServer(SocketServer.UDPServer):
  allow_reuse_address = True
  # i'm not sure having the server 'timeout' makes any sense
  # the correct non-lazy solution is a proper select loop
  timeout = None
  
  def __init__(self, server_address, RequestHandlerClass):
    # this appears to be somewhat system dependent
    # on linux2, (2.6 variants) it seems to be about 64k (65507)
    # on darwin, the default 8k seems to be the law of the land
    if sys.platform == 'linux2':
      self.max_packet_size = 64 * 1024
      
    SocketServer.UDPServer.__init__(self, server_address, RequestHandlerClass)
    self._run = True
    self._message_handler_map = {}
    self._cidr_list = spyglass.cidr.CIDRList(['127.0.0.1'])
    self._shutdown_handlers = []

  def set_ip_allow(self, cidr_list):
    self._cidr_list = spyglass.cidr.CIDRList(cidr_list)

  def server_activate(self):
    self.socket.settimeout(self.timeout)
    SocketServer.UDPServer.server_activate(self)

  def verify_request(self, request, client_address):
    ip = client_address[0]
    return ip in self._cidr_list

  def serve_forever(self):
    # Python 2.6 changes the behavior of the handle_request method in a
    # way which is incompatible with using signals as spyglass does.
    if sys.version_info[:2] >= (2, 6):
      _handle_request_method = self._handle_request_noblock
    else:
      _handle_request_method = self.handle_request

    while self._run:
      _handle_request_method()
    self._shutdown()

  def serve_forever(self):
    while self._run:
      self.handle_request()
    self._shutdown()
  
  def add_shutdown_handler(self, function, pargs=(), kargs=None):
    if kargs is None:
      kargs = {}
    self._shutdown_handlers.append((function, pargs, kargs))
    
  def _shutdown(self):
    log.debug('server shutdown')
    for function, pargs, kargs in self._shutdown_handlers:
      try:
        function(*pargs, **kargs)
      except:
        log.exception('error in SPUDP._shutdown')

  # callback = f(request_handler, msg_type, data)
  # callback is the name of a method on the object
  # it will be looked up at runtime via getattr
  def register_handler(self, msg_type, callback_name):
    msg_type = msg_type[:MSG_TYPE_SIZE].ljust(MSG_TYPE_SIZE, '.')
    self._message_handler_map[msg_type] = callback_name


