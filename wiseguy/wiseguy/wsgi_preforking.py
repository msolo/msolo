from fastcgi.WSGI import WSGIMixIn

from fcgi_server import FCGIServer
from preforking import PreForkingMixIn

class PreForkingWSGIServer(WSGIMixIn, PreForkingMixIn, FCGIServer):
    _environ = { 'wsgi.version':      (1,0),
                 'wsgi.multithread':  False,
                 'wsgi.multiprocess': True,
                 'wsgi.run_once':     False }

    def __init__(self, app, **kargs):
        FCGIServer.__init__(self, **kargs)
        self._app = app
    
