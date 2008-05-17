import logging
import pprint
import random
import time


leak_some_memory = []

def simple_app(environ, start_response):
  status = '200 OK'
  path = environ.get('PATH_INFO','')
  
  delay = None
  content = ''
  if path == '/delay':
    delay = random.normalvariate(15, 5) * 0.001
  elif path == '/long_delay':
    delay = 10
  elif path == '/leak':
    leak_some_memory.append('x' * 1024 * 1024)
  elif path == '/env':
    content = "%s\n" % pprint.pformat(environ)
  elif path == '/db_hang':
    import MySQLdb
    conn = MySQLdb.connect(host='localhost', user='', passwd='')
    c = conn.cursor()
    c.execute("select sleep(30);")
    content = "db done\n"
  elif path == '/exception':
    raise Exception("fcgi exception")
  if not content:
    content = "Hello from Wiseguy!\n"
    
  if delay:
    time.sleep(delay)

  response_headers = [
      ('Content-type','text/plain'),
      ('Content-length', str(len(content))),
      ]
  start_response(status, response_headers)
  return [content]
