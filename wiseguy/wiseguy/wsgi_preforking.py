from fastcgi.WSGI import WSGIMixIn
from wiseguy.fcgi_server import FCGIServer
from wiseguy.preforking import PreForkingMixIn

class PreForkingFCGIWSGIServer(WSGIMixIn, PreForkingMixIn, FCGIServer):
  _environ = {
    'wsgi.version': (1, 0),
    'wsgi.multithread': False,
    'wsgi.multiprocess': True,
    'wsgi.run_once': False
    }

  def __init__(self, app, **kargs):
    FCGIServer.__init__(self, **kargs)
    self._app = app

  def get_app(self):
    return _app

  def set_app(self, app):
    self._app = app

# backward compatibility
PreForkingWSGIServer = PreForkingFCGIWSGIServer
