from spyglass import event_collector
from spyglass.event_collector import EventCollectorException

sc = event_collector.EventCollector()
sc2 = event_collector.EventCollector()


def increment_some_keys(collector):
  for key in ('memcache.get.LVideo',
              'memcache.get.logic.video.LVideo',
              'RelatedResults'):
    for x in xrange(100):
      collector.increment(key)

increment_some_keys(sc)
increment_some_keys(sc2)
sc2.increment('Comments', 100)

def log_some_execs(collector):
  sample_exec_times = [0.012, 0.051, 0.0015, 1.000, 1.411]
  for exec_time in sample_exec_times:
    collector.log_exec_time('dummy_servlet', exec_time)

log_some_execs(sc)

sample_exec_times = [0.112, 0.551, 0.0015, 1.000, 1.411]
for exec_time in sample_exec_times:
  sc2.log_exec_time('dummy_servlet', exec_time)
  sc2.log_exec_time('dummy_servlet2', exec_time)

counter_test = {'memcache.get.logic.video.LVideo': 100, 'RelatedResults': 100, 'memcache.get.LVideo': 100}
exec_test = {'dummy_servlet': {0: 1, 1000: 1, 10: 1, 50: 1, 1410: 1}}

if sc.counter_map != counter_test:
  print "counter not collecting correct data"
if sc.exec_time_map != exec_test:
  print "exec_logger not collecting correct data"

sc.merge(sc2)

counter_merge_test = {'Comments': 100,
 'RelatedResults': 200,
 'memcache.get.LVideo': 200,
 'memcache.get.logic.video.LVideo': 200}
exec_merge_test = {'dummy_servlet': {0: 2, 1410: 2, 550: 1, 1000: 2, 10: 1, 110: 1, 50: 1},
 'dummy_servlet2': {0: 1, 1000: 1, 1410: 1, 110: 1, 550: 1}}

if sc.counter_map != counter_merge_test:
  print "counter not merging correct data"
  print "counter_map:"
  print sc.counter_map
  print "counter_merge_test:"
  print counter_merge_test


if sc.exec_time_map != exec_merge_test:
  print "exec_logger not merging correct data"

# print sc

gsc = event_collector.get_event_collector()
increment_some_keys(gsc)
event_collector.open_collector()
gsc2 = event_collector.get_event_collector()
increment_some_keys(gsc2)

#print gsc

try:
  event_collector.close_collector(gsc)
  print "unsafe collector close"
except EventCollectorException, e:
  pass

try:
  gsc.close()
  print "unsafe collector close"
except EventCollectorException, e:
  pass

#print gsc2
gsc2.close()

log_some_execs(gsc)
print gsc
print '\n'.join(gsc.get_log_lines(use_stats_analysis=True))

import pickle
data = pickle.dumps(gsc)
print "data size", len(data)
