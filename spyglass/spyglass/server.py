import collections
import copy
import errno
import logging
import os
import random
import re
import signal
import socket
import SocketServer
import sys
import time

import cPickle as pickle

import spyglass.event_collector
import spyglass.event_aggregator
import spyglass.decay_stats
import spyglass.deferred_io
import spyglass.spudp

from spyglass.msg_types import *
from spyglass.event_collector import is_valid_key

log = logging.getLogger('spyglass.server')


class RateMap(dict):
  # decay 1/5/15/60min 6hrs, 1 day, 1 week
  decays = (12, 60, 180, 720, 4320, 17280, 120960)
  period = 1

  def increment(self, key, increment, now=None):
    try:
      self[key].update(increment, now)
    except KeyError, e:
      self[key] = spyglass.decay_stats.MultiExpDecayCounter(
        self.decays, last_update=now,
        period=self.period)
  
  def merge(self, counter_map, now=None):
    for key, value in counter_map.iteritems():
      self.increment(key, value, now)

  def get_rate(self, key, decay_window, now=None):
    return self[key].counters[decay_window].get_value(now)
  
  def prune(self, maximum_inactivity=3600):
    expiration_time = time.time() - maximum_inactivity
    for key, counter in self.items():
      # note: these are all multi-rate counters, so just pick the first one
      # to represent the last update time
      if (counter.counters[0].last_update < expiration_time or
          not is_valid_key(key)):
        del self[key]
  
  # condense the execution data into a statistical distribution
  def get_log_lines(self, now=None, show_all_values=False):
    lines = []
    if now is None:
      now = time.time()
    for key, exp_counter in sorted(self.iteritems()):
      decayed_values = exp_counter.get_values(now)
      if not show_all_values:
        decayed_values = decayed_values[:3]
      
      rates = '/'.join(['%.02f' % x for x in decayed_values])
      lines.append('%s: %s' % (key, rates))
    return lines


class PeriodicTask(object):
  def __init__(self, function, pargs, kargs, execution_interval,
               alarm_interval):
    self.function = function
    self.pargs = pargs
    self.kargs = kargs
    self.execution_interval = execution_interval
    self.last_exec_time = 0
    self.update_probability = float(alarm_interval) / execution_interval

  def __call__(self, *pargs, **kargs):
    self.function(*self.pargs, **self.kargs)

  def __str__(self):
    return self.function.__name__
  
  @property
  def next_exec_time(self):
    return self.last_exec_time + self.execution_interval


class SpyglassServer(spyglass.spudp.SPUDPServer):
  alarm_interval = 30
  _restore_attributes = ('event_collector', 'rate_map', 'event_history')
  
  # maximum_counter_inactivity - time in seconds after which a rate counter is
  # considered stale and prunable
  def __init__(self, server_address, RequestHandlerClass, log_path=None,
      state_path=None, proc_path=None, enable_deferred_io=True,
      maximum_counter_inactivity=3600):
    spyglass.spudp.SPUDPServer.__init__(
      self, server_address, RequestHandlerClass)
    self.event_collector = spyglass.event_collector.EventCollector()
    self.rate_map = RateMap()
    self.event_history = spyglass.event_aggregator.EventHistory(16)
    self._state_path = state_path
    self._proc_path = proc_path
    self._restore_state()
    self.enable_deferred_io = enable_deferred_io
    self.periodic_tasks = []
    self.maximum_counter_inactivity = maximum_counter_inactivity
    
    if self.enable_deferred_io:
      self.dio_manager = spyglass.deferred_io.DeferredIOManager(logger=log)
      self.add_shutdown_handler(self.dio_manager.shutdown)
    else:
      self.dio_manager = None
    
    self.register_handler(MSG_TYPE_MERGE_EVENTS, 'handle_merge_events')
    self.register_handler(MSG_TYPE_PING, 'handle_ping')
    self.register_handler(MSG_TYPE_RATES, 'handle_rates')
    self.register_handler(MSG_TYPE_GET_RATE, 'handle_get_rate')
    self.register_handler(MSG_TYPE_GET_EVENTS, 'handle_get_events')
    self.register_handler(MSG_TYPE_GET_EXEC_SUMMARY,
                'handle_get_exec_lines')
    self.register_handler(MSG_TYPE_GET_SUMMARY, 'handle_get_summary')
    self.register_handler(MSG_TYPE_GET_LOAD_AVERAGE,
                'handle_get_load_average')
    self.register_handler(MSG_TYPE_GET_STATS, 'handle_get_stats')

    # checkpoint recovery state every 5 minutes
    self.register_periodic_task(self.rate_map.prune,
      (self.maximum_counter_inactivity,), {}, self.maximum_counter_inactivity)
    self.register_periodic_task(self._save_state, (), {}, 300)
    self.register_periodic_task(self.write_proc_file, (), {}, 30)
    
  # execution_interval - time in seconds between calls
  def register_periodic_task(self, function, pargs, kargs,
    execution_interval):
    self.periodic_tasks.append(
      PeriodicTask(function, pargs, kargs, execution_interval,
                   self.alarm_interval))

  def execute_periodic_tasks_by_time(self):
    now = time.time()
    for task in self.periodic_tasks:
      if now > task.next_exec_time:
        try:
          task()
          task.last_exec_time = now
          #log.info('periodic task: %s', task)
        except:
          log.exception('periodic task: %s', task)

  def execute_periodic_tasks_randomly(self):
    r = random.random()
    for task in self.periodic_tasks:
      if r < task.update_probability:
        try:
          task()
          #log.info('periodic task: %s', task)
        except:
          log.exception('periodic task: %s', task)

  execute_periodic_tasks = execute_periodic_tasks_by_time

  def _save_state(self):
    if not self._state_path:
      return
    log.debug('_save_state: %s', self._state_path)
    data = dict([(attr, getattr(self, attr))
           for attr in self._restore_attributes])
    fdata = pickle.dumps(data, pickle.HIGHEST_PROTOCOL)
    if self.enable_deferred_io:
      self.dio_manager.write_file(self._state_path, fdata)
    else:
      f = open(self._state_path, 'w')
      f.write(fdata)
      f.close()
  
  def _restore_state(self):
    if not self._state_path:
      return
    try:
      f = open(self._state_path)
    except IOError, e:
      if e[0] != errno.ENOENT:
        log.warning('IOError in _restore_state: %s', str(e))
      return
      
    try:
      data = pickle.load(f)
      for attr in self._restore_attributes:
        try:
          setattr(self, attr, data[attr])
        except KeyError, e:
          log.warning('ignoring missing restore attribute: %s', e[0])
    except (EOFError, Exception), e:
      log.exception('unable to restore state')
    f.close()
  
  def signal_handler(self, signal_number, frame):
    try:
      if signal_number in (signal.SIGTERM, signal.SIGINT):
        self._run = False
        self._save_state()
      elif signal_number == signal.SIGALRM:
        signal.alarm(self.alarm_interval)
        self.execute_periodic_tasks()
    except:
      log.exception('error in signal_handler')
  
  def write_proc_file(self):
    if not self._proc_path:
      return
    data = '\n'.join(self.rate_map.get_log_lines(show_all_values=True)) + '\n'
    if self.enable_deferred_io:
      self.dio_manager.write_file(self._proc_path, data)
    else:
      f = open(self._proc_path, 'w')
      f.write(data)
      f.close()
  

signal_list = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM)
def register_signal_handlers(server):
  for signal_number in signal_list:
    signal.signal(signal_number, server.signal_handler)

  signal.alarm(server.alarm_interval)


class SpyglassHandler(object):
  def get_exec_lines(self, minutes, lifetime=False):
    # lines = []
    # lines.append('minute: %s' % minute_list)
    # lines.append('wsgi.request: %s' % ec.counter_map['wsgi.request'])
    event_history = self.get_event_history()
    if lifetime:
      ec = event_history.lifetime_collector
    else:
      ec, minute_list = event_history.get_event_aggregate(minutes)
    lines = ec.exec_time_map.get_stats_log_lines()
    return lines

  def get_load_average_lines(self, rate_key='wsgi.request',
                             error_key='wsgi.error'):
    event_history = self.get_event_history()
    ec = event_history.get_lifetime_aggregate()
    lines = []
    lines.append(
      'response_count: %s' % ec.counter_map.get(rate_key, 0))
    lines.append('error_count: %s' % ec.counter_map.get(error_key, 0))
    req_avg = event_history.get_rate_avg(rate_key)
    req_avg_str = ' '.join(['%.2f' % x for x in req_avg])
    lines.append('req_averages: %s' % req_avg_str)
    return lines

  def get_stats_lines(self, details=False, minutes=1, lifetime=False):
    lines = self.get_load_average_lines()
    if details:
      if not (1 <= minutes <= 15):
        minutes = 1
      lines.extend(self.get_exec_lines(minutes, lifetime))
    return lines

  def get_rates_lines(self):
    return self.get_data_server().rate_map.get_log_lines()


# DatagramRequestHandler doesn't look that robust, let's use a home-grown
# thing for now.
class SpyglassRequestHandler(spyglass.spudp.SPUDPRequestHandler,
               SpyglassHandler):
  def log_message(self, format, *args):
    log.info(format, *args)

  def get_data_server(self):
    return self.server

  def get_event_history(self):
    return self.server.event_history

  def handle_merge_events(self, msg_type, data):
    event_collector = data['data']
    now = data['now']
    self.server.event_collector.merge(event_collector)
    self.server.rate_map.merge(event_collector.counter_map, now)
    self.server.event_history.merge(event_collector, now)
    
  def handle_ping(self, msg_type, data):
    return 'OK'

  def handle_rates(self, msg_type, data):
    return self.get_rates_lines()

  def handle_get_rate(self, msg_type, data):
    (key, decay_window) = data
    return self.server.rate_map.get_rate(key, decay_window)

  def handle_get_events(self, msg_type, data):
    return self.server.rate_map.keys()

  def handle_get_exec_lines(self, msg_type, data):
    (minutes, ) = data
    return '\n'.join(self.get_exec_lines(minutes))

  def handle_get_load_average(self, msg_type, data):
    (kargs, ) = data
    return '\n'.join(self.get_load_average_lines(**kargs))

  def handle_get_stats(self, msg_type, data):
    (args, kargs) = data
    lines = self.get_stats_lines(**kargs)
    return '\n'.join(lines)

  # data - a list of tuples [(aggregate_name, regex_pattern), ...]
  def handle_get_summary(self, msg_type, data):
    # log.info('handle_get_summary')
    aggregate_key_pattern_list = []
    for aggregate_key, pattern_string in data:
      aggregate_key_pattern_list.append((aggregate_key,
                         re.compile(pattern_string)))
    summary_map = {}
    for key, decay_counter in self.server.rate_map.iteritems():
      for aggregate_key, pattern in aggregate_key_pattern_list:
        if not pattern.match(key):
          continue
        rate = decay_counter.counters[0].get_value()
        try:
          # computing more than we need here
          summary_map[aggregate_key] += rate
        except KeyError:
          summary_map[aggregate_key] = rate
    return summary_map
      
  
def create_udp_server(server_address, **kargs):
  server = SpyglassServer(server_address, SpyglassRequestHandler, **kargs)
  register_signal_handlers(server)
  return server


def test_rate_map():
  now = 1
  start = 1
  keys = ('test1', 'test10', 'test100',)
  req_rates = (1, 10, 100,)
  rate_map = RateMap()
  counter = spyglass.decay_stats.MultiExpDecayCounter(
    spyglass.decay_stats.fast_decays,
    last_update=now,
    init=1,
    period=1)
  for x in xrange(600):
    for key, req_rate in zip(keys, req_rates):
      # print key, req_rate, now+x
      rate_map.increment(key, req_rate + x, now + x)
    counter.update(req_rate + x, now+x)
    if x and x % 60 == 0:
      print '\n'.join(rate_map.get_log_lines(now + x))
      print "counter", counter.get_values(now + x)
      print
      
