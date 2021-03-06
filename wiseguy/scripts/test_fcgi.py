#!/usr/bin/env python

import logging
import pprint
import random
import sys
import time

import wiseguy.fcgi_server
import wiseguy.preforking

from wiseguy.wsgi_preforking import PreForkingWSGIServer

leak_some_memory = []

def simple_app(environ, start_response):
    status = '200 OK'
    script_name = environ['SCRIPT_NAME']
    delay = None
    content = ''
    
    if script_name == '/fcgi/delay':
        delay = random.normalvariate(15, 5) * 0.001
    elif script_name == '/fcgi/long_delay':
        delay = 10
    elif script_name == '/fcgi/leak':
        leak_some_memory.append('x' * 1024 * 1024)
    elif script_name == '/fcgi/env':
        content = "%s\n" % pprint.pformat(environ)
    elif script_name == '/fcgi/db':
        import MySQLdb
        conn = MySQLdb.connect(host='localhost', user='root', passwd='mysqls3rv3r')
        c = conn.cursor()
        c.execute("select sleep(30);")
        content = "db done\n"
    elif script_name == '/fcgi/exception':
        raise Exception, "crap"
    if not content:
        content = "My Own Hello World!\n"
        
    if delay:
        time.sleep(delay)

    response_headers = [('Content-type','text/plain'), ('Content-length', str(len(content)))]
    start_response(status, response_headers)
    return [content]

if __name__ == '__main__':
    from optparse import OptionParser, OptionValueError

    def validate_bind_address(option, opt_str, value, parser):
        try:
            host, port = value.split(':')
            setattr(parser.values, option.dest, (host, int(port)))
        except ValueError:
            raise OptionValueError("%s option invalid" % opt_str)

    def validate_log_level(option, opt_str, value, parser):
        try:
            log_level = logging.getLevelName(value)
            setattr(parser.values, option.dest, int(log_level))
        except ValueError:
            raise OptionValueError("%s error, unknown log level: %s" %
                                   (opt_str, value))

    parser = OptionParser()
    parser.add_option("--bind-address",
                      dest="bind_address",
                      action="callback",  callback=validate_bind_address,
                      type="str", nargs=1,
                      help="main wsgi listener")
    parser.add_option("--management-address",
                      dest="management_address",
                      action="callback",  callback=validate_bind_address,
                      type="str", nargs=1,
                      help="http management port")
    parser.add_option("--max-requests",
                      dest="max_requests", default=None,
                      type="int",
                      help="max requests handled per child")
    parser.add_option("--max-rss",
                      dest="max_rss", default=None,
                      type="int",
                      help="max rss before a child gets a SIGTERM")
    parser.add_option("--workers",
                      dest="workers", default=1,
                      type="int",
                      help="number of worker processes")
    parser.add_option("--log-level", default=logging.INFO,
                      action="callback", callback=validate_log_level,
                      type="str", nargs=1,
                      help="set the base log level")
    parser.add_option("--profile-path", default=None,
                      help="log hotshot profile data to this path")
    parser.add_option("--profile-uri", default=None,
                      help="regex matching which uri's to profile")
                      
                      
    (options, args) = parser.parse_args()

    logging.basicConfig(level=options.log_level)

    s = PreForkingWSGIServer(simple_app,
                             server_address=options.bind_address,
                             management_address=options.management_address,
                             stats_address=options.stats_address,
                             workers=options.workers,
                             max_requests=options.max_requests,
                             max_rss=options.max_rss,
                             profile_path=options.profile_path,
                             profile_uri=options.profile_uri)
    s.serve_forever()
    
