'''
    PricklyNettles
    TODO:
    1) Securify the module loading process
    2) Check module loading to see if module is in sys.path already
    3) Build RegExRoutesApp as subclass
'''
import logging
import pprint
import random
import time
import sys
from wiseguy.examples.routes.basecontroller import BaseController

'''
    See notes above
    See also the load_controller function
'''
modulepath = 'wiseguy.examples.routes.'

'''
    Some simple samples. Probably move to config or db or whatever
    you like for getting routes. memcache might work nicely too
'''
routes = []
routes.append(('/', 'Controller.index'))
routes.append(('/hello', 'Controller.hello'))

class RoutesApp():
    def __init__(self, routes=None):
        if routes == None:
            routes = []
        self.routes = routes
        
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO','')

        for route in self.routes:
            if path == route[0]:
                module_name, func_name = route[1].split('.', 1)
                controller = self.load_controller(module_name)
                ctrl = controller(environ, start_response)
                func = getattr(ctrl, func_name)
                return func()

        ctrl = BaseController(environ, start_response)
        return ctrl.send404()

    def load_controller(self, modulename):
        try:
            module = __import__(modulepath + modulename.lower(), globals(), locals(), [modulename])
        except ImportError:
            return None
        return vars(module)[modulename]


app = RoutesApp(routes)
    
