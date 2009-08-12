import BaseHTTPServer
import cgi
import errno
import httplib
import logging
import select
import threading
import urllib
import urlparse

import wiseguy

class EmbeddedHTTPServer(BaseHTTPServer.HTTPServer):
  thread_name = 'embedded_http_server'
  allow_reuse_address = True
  server_version = 'wiseguy/' + wiseguy.__version__
  teardown_timeout = 2.0
  _bound = False
  _activated = False
  
  def __init__(self, server_address, RequestHandlerClass, **kargs):
    self._quit = False
    self._thread = None
    BaseHTTPServer.HTTPServer.__init__(
      self, server_address, RequestHandlerClass, **kargs)

  def __str__(self):
    return '<%s@%s>' % (self.__class__.__name__, self.server_address)

  def server_bind(self):
    BaseHTTPServer.HTTPServer.server_bind(self)
    self._bound = True

  def server_activate(self):
    BaseHTTPServer.HTTPServer.server_activate(self)
    self._activated = True

  def get_request(self):
    # Running under Linux the select() call can return, even when there isn't
    # data, so accept() will hang anyway. This of course blows, so do this
    # as non-blocking temporarily and restor whatever mischief was there to
    # begin with. Beginning to wonder if the only reasonable way to do a python
    # web server is with the dreaded asynchat.
    old_timeout = self.socket.gettimeout()
    try:
      self.socket.settimeout(0.0)
      return BaseHTTPServer.HTTPServer.get_request(self)
    finally:
      self.socket.settimeout(old_timeout)
  
  def start(self):
    if not self._bound:
      self.server_bind()
    if not self._activated:
      self.server_activate()
    self._thread = threading.Thread(
      target=self.serve_forever, name=self.thread_name)
    self._thread.setDaemon(True)
    self._thread.start()    

  def stop(self):
    self._quit = True
    # fixme: not needed in python2.6
    # tickle the server so we break out of the loop nicely
    try:
      urllib.urlopen('http://127.0.0.1:%s/__quit__' % self.server_port)
    finally:
      self._thread.join(self.teardown_timeout)

  def serve_forever(self):
    try:
      logging.info('started %s', self)
      # fixme: not needed in python2.6
      while not self._quit:
        try:
          self.handle_request()
        except select.error, e:
          # a call to setuid() can cause your threads to receive an untrappable
          # signal, SIGRT_1 (at least on Linux)
          # fixme: this should probably go to the std library
          if e[0] == errno.EINTR:
            pass
          else:
            raise
    except KeyboardInterrupt:
      pass
    logging.info('shutdown %s', self)


class EmbeddedRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  path_map = {
    '/': 'handle_default',
  }

  response_code = httplib.OK
  content_type = 'text/plain; charset=utf-8'

  @classmethod
  def register_handler(cls, url, function):
    cls.path_map[url] = function

  @property
  def send_client_html(self):
    return 'html' in self.headers.getheader('accept')

  def _get_int(self, name, default=None):
    try:
      return int(self.form[name][0])
    except (KeyError, IndexError, ValueError), e:
      return default

  def _get_float(self, name, default=None):
    try:
      return float(self.form[name][0])
    except (KeyError, IndexError, ValueError), e:
      return default

  def _get_str(self, name, default=''):
    try:
      return self.form[name][0]
    except (KeyError, IndexError), e:
      return default

  def do_GET(self):
    scheme, netloc, path, query, fragment = urlparse.urlsplit(self.path)
    self.form = cgi.parse_qs(query, keep_blank_values=True)
    path = urllib.url2pathname(path)
    self.handle_path(path)

  def do_POST(self):
    scheme, netloc, path, query, fragment = urlparse.urlsplit(self.path)
    try:
      self.form = cgi.parse(self.rfile)
      path = urllib.url2pathname(path)
      self.handle_path(path)
    except Exception:
      logging.exception('bad POST')
      self.send_error(httplib.BAD_REQUEST)

  def send_data(self, response_data):
    self.send_response(self.response_code)
    self.send_header('Cache-Control', 'no-cache')
    self.send_header('Content-Length', len(response_data))
    self.send_header('Content-Type', self.content_type)
    self.end_headers()
    self.wfile.write(response_data)

  def handle_path(self, path):
    try:
      handler_name = self.path_map[path]
      if isinstance(handler_name, str):
        handler = getattr(self, handler_name)
      else:
        # note: handle direct assignment of a callable - maybe we don't need
        # to do it here - seems like you just subclass
        _handler = handler_name
        def handler():
          return _handler(self)
    except (KeyError, AttributeError), e:
      return self.send_error(httplib.NOT_FOUND)

    try:
      self.send_data(handler())
    except:
      logging.exception("EmbeddedRequestHandler error")
      return self.send_error(httplib.INTERNAL_SERVER_ERROR)

  def handle_default(self):
    if self.send_client_html:
      self.content_type = 'text/html; charset=utf-8'
      response_data = '\n'.join(['<a href="%(path)s">%(path)s</a><br>' %
                               {'path': x}
                               for x in sorted(self.path_map.iterkeys())])
    else:
      response_data = '\n'.join(sorted(self.path_map.iterkeys()))
    response_data += '\n'
    return response_data

  def log_message(self, format, *args):
    logging.info(self.address_string() + " " + format, *args)
