import logging
import socket
import time

import cPickle as pickle

import spyglass.event_collector
import spyglass.spudp
from spyglass.msg_types import *

class SpyglassException(Exception):
  pass

class SpyglassClient(spyglass.spudp.SPUDPClient):

  def ping(self):
    return self._send_recv(MSG_TYPE_PING)

  def get_rate(self, key, decay_window):
    return self._send_recv(MSG_TYPE_GET_RATE, (key, decay_window))

  def get_rates(self):
    return self._send_recv(MSG_TYPE_RATES)

  def get_events(self):
    return self._send_recv(MSG_TYPE_GET_EVENTS)

  def get_summary(self, aggregate_key_pattern_list):
    return self._send_recv(MSG_TYPE_GET_SUMMARY, aggregate_key_pattern_list)

  def get_exec_summary(self, minutes):
    return self._send_recv(MSG_TYPE_GET_EXEC_SUMMARY, (minutes,))

  def get_load_avg(self):
    return self._send_recv(MSG_TYPE_GET_LOAD_AVERAGE)

  def get_stats(self, details=1, lifetime=False, minutes=1):
    kargs = {'details': details,
             'lifetime': lifetime,
             'minutes': minutes,
             }
    return self._send_recv(MSG_TYPE_GET_STATS, ((), kargs))

  def send_events(self, event_collector, now=None):
    payload = {
      'data':event_collector,
      'now':now,
      }
    try:
      self._send(MSG_TYPE_MERGE_EVENTS, payload)
    except socket.error, e:
      logging.error("error sending stats data: %s", e)
      

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
  parser.add_option("--stats-address",
                    dest="stats_address",
                    action="callback",  callback=validate_bind_address,
                    type="str", nargs=1,
                    help="send stats via udp")
  parser.add_option("--log-level", default=logging.INFO,
                    action="callback", callback=validate_log_level,
                    type="str", nargs=1,
                    help="set the base log level")
  parser.add_option("--test", default=False,
                    action="store_true",
                    help="run tests against a server")

  (options, args) = parser.parse_args()

  logging.basicConfig(level=options.log_level)
  s = SpyglassClient(options.stats_address)

  for arg in args:
    if arg == 'ping':
      print 'ping', s.ping()
    elif arg == 'exec_stats_1':
      print s.get_exec_summary(1)
    elif arg == 'exec_stats_5':
      print s.get_exec_summary(5)
    elif arg == 'exec_stats_15':
      print s.get_exec_summary(15)

  if options.test:
    import spyglass.event_collector
    ec = spyglass.event_collector.EventCollector()
    for x in range(10):
      ec.increment('test.%u' % x)
      ec.log_exec_time('test_exec', 10 * x)
      
    ec.increment('test')
    print 'ping:', s.ping() == 'OK'
    for x in xrange(50):
      s.send_events(ec)
    rates = s.get_rates()
    if type(rates) != str:
      print 'error get_rates'
    else:
      print 'get_rates:', rates
    rate = s.get_rate('test', 0)
    if type(rate) not in (int, long, float):
      print 'error get_rate', type(rate)
    else:
      print 'get_rate:', rate

    events = s.get_events()
    if type(events) != list:
      print 'error get_events'
    else:
      print "events:", events
      
    summary = s.get_summary([('test', '^test\.'),])
    print "summary:", summary

    exec_summary = s.get_exec_summary(1)
    print "exec summary:", exec_summary
