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
  def __init__(self, max_history, bucket_interval=60):
    # add one so we have a current bucket that's taking new events
    # while maintaining the appropriate amount of history
    self.max_size = int(max_history / bucket_interval) + 1
    self.bucket_interval = bucket_interval
    self.event_collector_map = {}
    self.event_collector_deque = collections.deque()
    self.lifetime_collector = spyglass.event_collector.EventCollector()
    self.rate_map = {}

  def _timestamp_to_bucket_time(self, timestamp):
    timestamp = int(timestamp)
    return timestamp - (timestamp % self.bucket_interval)

  def _add_bucket(self, timestamp):
    bucket_time = self._timestamp_to_bucket_time(timestamp)
    ec = spyglass.event_collector.EventCollector()
    self.event_collector_deque.append(bucket_time)
    self.event_collector_map[bucket_time] = ec
    if len(self.event_collector_deque) > self.max_size:
      removed_bucket_time = self.event_collector_deque.popleft()
      del self.event_collector_map[removed_bucket_time]
    return ec

  def _get_by_timestamp(self, timestamp):
    bucket_time = self._timestamp_to_bucket_time(timestamp)
    try:
      return self.event_collector_map[bucket_time]
    except KeyError, e:
      return self._add_bucket(bucket_time)

  def merge(self, event_collector, now=None):
    if now is None:
      now = time.time()
    ec = self._get_by_timestamp(now)
    ec.merge(event_collector)
    self.lifetime_collector.merge(event_collector)

  # return several buckets of aggregate events
  def get_event_aggregate(self, buckets):
    ec = spyglass.event_collector.EventCollector()
    # skip the newest bucket - it's in a state of inconsistency
    bucket_list = []
    for i, bucket_time in enumerate(reversed(self.event_collector_deque)):
      if 1 <= i <= bucket_time:
        bucket_list.append(bucket_time)
        ec.merge(self.event_collector_map[bucket_time])
    return ec, bucket_list

  def get_lifetime_aggregate(self):
    return self.lifetime_collector

  def get_rate_avg(self, key):
    ec_list = []
    bucket_deque = copy.copy(self.event_collector_deque)
    # remove the current minute which won't be stable
    try:
      minute_deque.pop()
      ec_list = [self.event_collector_map[bucket_time]
                 for bucket_time in bucket_deque]
      return event_rate_avg(
        ec_list, (key,), bucket_interval=self.bucket_interval)[key]
    except IndexError, e:
      return 0.0, 0.0, 0.0

    
# @return (1m, 5m, 15m) avg events/second over the given time ranges
# @param event_collector_list - sorted list of event_collectors - the most
# recent item time-wise should be the last item in the list
# @param keys - a list of keys that we are interested in - None is 'all'
def event_rate_avg(event_collector_list, keys=None,
                   time_list=(1*60,5*60,15*60),
                   bucket_interval=60):
  ec_list = [spyglass.event_collector.EventCollector() for x in time_list]
  # fixme: a waste if you are only picking out one key
  bucket_list = [(x / bucket_interval) for x in time_list]  
  ec_bucket_list = zip(ec_list, bucket_list)
  max_bucket = max(bucket_list)
  for i, event_collector in enumerate(reversed(event_collector_list)):
    if i >= max_bucket:
      break
    for ec, bucket in ec_bucket_list:
      if i < bucket:
        ec.merge(event_collector)

  rate_map = {}
  for key in keys:
    rate_list = []
    for ec, time_window in zip(ec_list, time_list):
      try:
        avg = ec.counter_map[key] / float(time_window)
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

