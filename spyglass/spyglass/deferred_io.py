# allow to writing whole files in a thread - no notion of error reporting
# the premise is that eventually, the file will get written. obviously this
# isn't suitable for general purpose stuff, but this should help when the
# disks are all loaded up and we are trying to write the procfile

from Queue import Queue, Full
from threading import Thread

import logging
import os
import time


class DeferredIOError(IOError):
  pass


class QueueItem(object):
  def __init__(self, function, pargs, kargs):
    self.function = function
    self.pargs = pargs
    self.kargs = kargs

  def handle(self):
    self.function(*self.pargs, **self.kargs)


class StopQueueItem(object):
  def __init__(self, thread_name):
    self.thread_name = thread_name


default_buffer_size = 1024 * 1024

class DeferredIOManager(object):
  
  def __init__(self, qsize=10, iothreads=1, logger=None):
    self.buffer_size = default_buffer_size
    self.job_queue = Queue(qsize)
    self.completion_queue = Queue(qsize)
    if logger is None:
      logger = logging
    self.logger = logger
    self.thread_pool = []
    for x in xrange(iothreads):
      thread_name = 'deferred-io-%s' % x
      t = Thread(target=self.drain_io_queue, name=thread_name)
      self.thread_pool.append(t)
      t.setDaemon(True)
      t.start()

  def shutdown(self):
    for t in self.thread_pool:
      self.job_queue.put(StopQueueItem(t.getName()))
    for t in self.thread_pool:
      t.join()

  def drain_io_queue(self):
    while True:
      qitem = self.job_queue.get()
      if type(qitem) is StopQueueItem:
        break
      try:
        qitem.handle()
      except:
        logging.exception('error in drain_io_queue')

  # write out a whole file, errors aren't really reported very well with an
  # explicit exception - they are just log
  def write_file(self, *pargs, **kargs):
    try:
      self.job_queue.put_nowait(QueueItem(self._write_file, pargs, kargs))
    except Full:
      raise DeferredIOError("deferred io queue full")

  async_write_file = write_file

  def _write_file(self, filename, data, atomic=True):
    sync_write_file(filename, data, atomic, self.buffer_size)

def sync_write_file(filename, data, atomic=True,
                    buffer_size=default_buffer_size):
  if atomic:
    tmp_path = filename + '.tmp'
  else:
    tmp_path = filename
  f = open(tmp_path, 'w', buffer_size)
  f.write(data)
  f.close()
  if atomic:
    os.rename(tmp_path, filename)
