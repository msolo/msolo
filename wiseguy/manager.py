# management tools for wiseguy
# the idea is to listen on a socket (tcp or udp) and accept commands
# that can affect the child processes - mostly killing existing or spawning
# new ones. this is not a general purpose back door to modify values inside
# child processes

import BaseHTTPServer
import cgi
import logging
import os.path
import sys
import traceback
import urllib
import urlparse

log = logging.getLogger('wsgi.manager')

class WiseguyManagerException(Exception):
	pass

class EmbeddedHTTPServer(BaseHTTPServer.HTTPServer):
	allow_reuse_address = True
	timeout = 0.1

	def __init__(self, server_address, RequestHandlerClass, fcgi_server):
		BaseHTTPServer.HTTPServer.__init__(self, server_address,
																			 RequestHandlerClass)
		self.fcgi_server = fcgi_server
	
	def server_activate(self):
		# NOTE: this is some fairly sketchy use of timeouts. The right way to do
		# this is proabably to run an explicit select loop, but this is so much
		# easier in the short term. (that's pretty much what's going on under the
		# hood anyway)
		self.socket.settimeout(self.timeout)
		BaseHTTPServer.HTTPServer.server_activate(self)

	def verify_request(self, request, client_address):
		# FIXME: CIDR allow?
		return client_address[0] == '127.0.0.1'

class WGManagerRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
	path_map = {
		'/': 'handle_default',
		'/server-cycle': 'handle_server_cycle',
		'/server-profile': 'handle_server_profile',
		'/server-profile-memory': 'handle_profile_memory',
		'/server-suspend-spawning': 'handle_suspend_spawning',
		'/server-resume-spawning': 'handle_resume_spawning',
		'/server-set-max-rss': 'handle_set_max_rss',
		'/server-setvar': 'handler_server_setvar',
# 		'/py-cmd': 'handle_py_cmd',
		}
	
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

	def _get_int(self, form, name, default):
		try:
			value = int(form[name][0])
		except (KeyError, IndexError, ValueError), e:
			value = default
		return value

	def handle_set_max_rss(self, path, form):
		max_rss = self._get_int(form, 'max_rss', 0)
		try:
			self.server.fcgi_server.set_max_rss(max_rss)
			self.send_data('OK.\n')
		except ValueError, e:
			log.warning('ignored bizzare max_rss: %s', max_rss)
			self.send_data('ERROR.\n%s\n' % e)

	def handle_resume_spawning(self, path, form):
		self.server.fcgi_server.set_allow_spawning(True)
		self.send_data('OK.\n')

	def handle_suspend_spawning(self, path, form):
		self.server.fcgi_server.set_allow_spawning(False)
		self.send_data('OK.\n')

	def handle_server_cycle(self, path, form):
		skew = self._get_int(form, 'skew', 0)
		workers = self._get_int(form, 'workers', None)
		force = self._get_int(form, 'force', False)

		self.server.fcgi_server.handle_server_cycle(skew, workers, force)
		self.send_data('cycled.\n')
		
	def handle_server_profile(self, path, form):
		try:
			profile_path = form['profile_path'][0]
		except (KeyError, IndexError), e:
			profile_path = '/tmp'

		try:
			profile_uri = form['profile_uri'][0]
		except (KeyError, IndexError), e:
			profile_uri = None
		
		request_count = self._get_int(form, 'request_count', 1000)

		self.server.fcgi_server.handle_server_profile(
			profile_path, profile_uri, request_count)
		self.send_data('starting profiler.\n')

	# note: this sets a variable in the parent - now you need
	# to cycle the children to actually collect data
	def handle_profile_memory(self, path, form):
		enable = self._get_int(form, 'enable', 0)
		min_delta = self._get_int(form, 'min_delta', 0)
		self.server.fcgi_server.set_profile_memory(enable, min_delta)
		self.server.fcgi_server.handle_server_cycle()
		if enable:
			self.send_data('set memory profiler: on.\n')
		else:
			self.send_data('set memory profiler: off.\n')

	def handle_py_cmd(self, path, form):
		try:
			src = form['src'][0]
		except (KeyError, IndexError), e:
			return self.send_data('No src.\n', 400)

		exec src
		try:
			response_data = str(response_data)
		except NameError, e:
			response_data = 'no response'
		
		self.send_data(response_data + '\n')

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

def create_http_server(server_address, fcgi_server):
	httpd = EmbeddedHTTPServer(server_address, WGManagerRequestHandler,
														 fcgi_server)
	return httpd


