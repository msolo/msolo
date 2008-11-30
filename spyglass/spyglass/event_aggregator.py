import collections
import copy
import errno
import logging
import time

import cPickle as pickle

import spyglass.event_collector

# maintain a number of buckets to handle a short history of counter values
# items are merged into the head bucket - once there are more than max_size
# buckets, we prune from the tail as needed
# buckets are assumed to be per-minute
# in this case, a bucket is really an EventCollector
class EventHistory(object):
  def __init__(self, max_size):
    self.max_size = max_size
    self.event_collector_map = {}
    self.event_collector_deque = collections.deque()
    self.lifetime_collector = spyglass.event_collector.EventCollector()

  def _add_bucket(self, minute):
    ec = spyglass.event_collector.EventCollector()
    self.event_collector_deque.append(minute)
    self.event_collector_map[minute] = ec
    if len(self.event_collector_deque) > self.max_size:
      removed_minute = self.event_collector_deque.popleft()
      del self.event_collector_map[removed_minute]
    return ec

  def _get_by_minute(self, minute):
    try:
      return self.event_collector_map[minute]
    except KeyError, e:
      return self._add_bucket(minute)

  def merge(self, event_collector, now=None):
    if now is None:
      now = time.time()
    minute = _time_to_minute(now)
    ec = self._get_by_minute(minute)
    ec.merge(event_collector)
    self.lifetime_collector.merge(event_collector)

  # return several minutes of aggregate events
  def get_event_aggregate(self, minutes):
    ec = spyglass.event_collector.EventCollector()
    # skip the newest bucket - it's in a state of inconsistency
    minute_list = []
    for i, minute in enumerate(reversed(self.event_collector_deque)):
      if 1 <= i <= minutes:
        minute_list.append(minute)
        ec.merge(self.event_collector_map[minute])
    return ec, minute_list

  def get_lifetime_aggregate(self):
    return self.lifetime_collector

  def get_rate_avg(self, key):
    ec_list = []
    minute_deque = copy.copy(self.event_collector_deque)
    # remove the current minute which won't be stable
    try:
      minute_deque.pop()
      ec_list = [self.event_collector_map[minute] for minute in minute_deque]
      return event_rate_avg(ec_list, (key,))[key]
    except IndexError, e:
      return 0.0, 0.0, 0.0

    
# @return (1m, 5m, 15m) avg events/second over the given time ranges
# @param event_collector_list - sorted list of event_collectors - the most
# recent item time-wise should be the last item in the list
# @param keys - a list of keys that we are interested in - None is 'all'
def event_rate_avg(event_collector_list, keys=None):
  ec_1m = spyglass.event_collector.EventCollector()
  ec_5m = spyglass.event_collector.EventCollector()
  ec_15m = spyglass.event_collector.EventCollector()
  # fixme: a waste if you are only picking out one key
  for i, event_collector in enumerate(reversed(event_collector_list)):
    if i < 1:
      ec_1m = event_collector
    # fixme: wasted merge work here
    if i < 5:
      ec_5m.merge(event_collector)
    if i < 15:
      ec_15m.merge(event_collector)
    else:
      break

  rate_map = {}
  for key in keys:
    rate_list = []
    for counter_map, time_window in ((ec_1m.counter_map, 60.0),
                     (ec_5m.counter_map, 60.0 * 5),
                     (ec_15m.counter_map, 60.0 * 15)):
      try:
        avg = counter_map[key] / time_window
      except KeyError:
        avg = 0.0
      rate_list.append(avg)
    rate_map[key] = rate_list
  return rate_map



# @return (1m, 5m, 15m) avg requests/second
def request_avg(stats_bucket_deque):
  reqs_1m = []
  reqs_5m = []
  reqs_15m = []
  
  for i, (bucket, bucket_set) in enumerate(reversed(stats_bucket_deque)):
    count = bucket.response_count + bucket.error_count
    count = count / (float(bucket.merge_count) / bucket.max_processes)
    if i < 1:
      reqs_1m.append(count)
    if i < 5:
      reqs_5m.append(count)
    if i < 15:
      reqs_15m.append(count)
    else:
      break

  try:
    req_avg_1m = sum(reqs_1m) / float(len(reqs_1m)) / 60.0
  except ZeroDivisionError:
    req_avg_1m = 0.0
    
  try:
    req_avg_5m = sum(reqs_5m) / float(len(reqs_5m)) / 60.0
  except ZeroDivisionError:
    req_avg_5m = 0.0

  try:
    req_avg_15m = sum(reqs_15m) / float(len(reqs_15m)) / 60.0
  except ZeroDivisionError:
    req_avg_15m = 0.0

  return req_avg_1m, req_avg_5m, req_avg_15m

def _time_to_minute(now):
  now = int(now)
  return now - (now % 60)

