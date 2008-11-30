# small http server to send back stats

import BaseHTTPServer
import cgi
import logging
import os.path
import sys
import threading
import traceback
import urllib
import urlparse

import spyglass.server

log = logging.getLogger('spyglass.stats_server')

class EmbeddedHTTPServer(BaseHTTPServer.HTTPServer):
  allow_reuse_address = True

  def __init__(self, server_address, RequestHandlerClass, spyglass_server):
    BaseHTTPServer.HTTPServer.__init__(self, server_address,
                                       RequestHandlerClass)
    self.spyglass_server = spyglass_server
    self._cidr_list = spyglass.cidr.CIDRList(['127.0.0.1'])

  def set_ip_allow(self, cidr_list):
    self._cidr_list = [spyglass.cidr.CIDR(cidr_str) for cidr_str in cidr_list]

  def verify_request(self, request, client_address):
    ip = client_address[0]
    return ip in self._cidr_list

class StatsRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler,
                          spyglass.server.SpyglassHandler):
  path_map = {
    '/': 'handle_default',
    '/server-stats': 'handle_server_stats',
    '/server-rates': 'handle_server_rates',
    }

  def get_data_server(self):
    return self.server.spyglass_server

  def get_event_history(self):
    return self.server.spyglass_server.event_history
  
  def do_GET(self):
    scheme, netloc, path, query, fragment = urlparse.urlsplit(self.path)
    form = cgi.parse_qs(query, keep_blank_values=True)
    path = urllib.url2pathname(path)
    self.handle_path(path, form)

  def handle_path(self, path, form):
    try:
      handler = getattr(self, self.path_map[path])
    except (KeyError, AttributeError), e:
      self.send_data('Not Found\n', 404)
    try:
      handler(path, form)
    except:
      tb = traceback.format_exc()
      self.send_data('Internal Server Error\n\n%s' % tb, 500)

  def handle_default(self, path, form):
    response_data = 'ack.\n'
    response_data += '\n'.join(self.path_map.iterkeys())
    response_data += '\n'
    self.send_data(response_data)

  def handle_server_stats(self, path, form):
    details = self._get_int(form, 'details', 0)
    lifetime = self._get_int(form, 'lifetime', 0)
    minutes = self._get_int(form, 'minutes', 0)
    summarize = self._get_int(form, 'summarize', 0)
    response_data = '\n'.join(self.get_stats_lines(
      details, minutes, lifetime))
    self.send_data(response_data + '\n')

  def handle_server_rates(self, path, form):
    response_data = '\n'.join(self.get_rates_lines())
    self.send_data(response_data + '\n')

  def _get_int(self, form, name, default):
    try:
      value = int(form[name][0])
    except (KeyError, IndexError, ValueError), e:
      value = default
    return value


  def send_data(self, response_data, response_code=200,
                content_type='text/html; charset=utf-8'):
    self.send_response(response_code)
    self.send_header('Cache-Control', 'no-cache')
    self.send_header('Content-Type', content_type)
    self.send_header('Content-Length', len(response_data))
    self.end_headers()
    self.wfile.write(response_data)

  def log_message(self, format, *args):
    log.info(format, *args)

def create_http_server(server_address, spyglass_server):
  httpd = EmbeddedHTTPServer(server_address, StatsRequestHandler,
                             spyglass_server)
  return httpd

def spawn_http_server_thread(server_address, spyglass_server):
  httpd = create_http_server(server_address, spyglass_server)
  t = threading.Thread(target=httpd.serve_forever, name='HTTP stats server')
  t.setDaemon(True)
  t.start()
