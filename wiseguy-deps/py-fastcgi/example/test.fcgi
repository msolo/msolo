#!/usr/bin/env python

import fastcgi

def simple_app(environ, start_response):
    #print "simple_app"
    """Simplest possible application object"""
    status = '200 OK'
    content = "My Own Hello World!\n"
    response_headers = [('Content-type','text/plain'), ('Content-length', str(len(content)))]
    start_response(status, response_headers)
    return [content]

s = fastcgi.ForkingWSGIServer(simple_app, workers=5)
#s = fastcgi.ThreadedWSGIServer(simple_app, workers=5)
s.serve_forever()
