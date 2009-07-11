#!/usr/bin/env python2.6

import logging
format='%(levelname)s %(name)s %(process)d:%(threadName)s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=format)
import sys


from wiseguy.http_server import PreForkingHTTPWSGIServer

leak = []

def hello_world_app(environ, start_response):
  status = '200 OK' # HTTP Status
  headers = [('Content-type', 'text/plain')] # HTTP Headers
  start_response(status, headers)

  # leak some memory to test the resource manager
  x = 'x' * 10 * 1024 * 1024
  leak.append(x)
  # The returned object is going to be printed
  return ["Hello World"]

httpd = PreForkingHTTPWSGIServer(
  hello_world_app,
  ('', 8000),
  management_address=('', 8001),
  fd_server_address='/tmp/test_managed_app-fd_server.sock',
  workers=1,
  max_requests=5)
print "Serving on port 8000..."

#import pytrace
#sys.settrace(pytrace.trace_function)

# Serve until process is killed
httpd.serve_forever()
