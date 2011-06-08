import errno
import logging
import subprocess
import sys

log = logging.getLogger('wsgi')

class MemoryException(Exception):
  pass

def generic_get_memory_usage(pid):
  """
  get memory usage (rss) of a child by executing ps - this is pretty ghetto
  i cannot find a programmatic api that does this correctly on both bsd and
  linux platforms - there are long discussions on Python mailing lists about
  this with no apparently resolution.

  this is especially nasty since the Mac OS X version of this only provides
  the ability to look at 1 process at a time, and only show RSS and VSS.
  arguably, these are the most useful anyway
  """
  cmd = ['ps', '-orss,vsz', '-p', str(pid)]
  try:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, close_fds=True)
    # if you don't wait, you leak file descriptors
    proc.wait()
  except OSError, e:
    if e[0] in (errno.EINTR,):
      raise MemoryException("interrupted during wait()")
    else:
      logging.exception("unexpected error in get_memory_usage")
      raise MemoryException("unexpected error: %s" % e)
  lines = proc.stdout.readlines()
  try:
    rss_size_kb, vsz_kb = lines[-1].strip().split()
    rss_size_kb, vsz_kb = int(rss_size_kb), int(vsz_kb)
  except ValueError:
    # logging.exception("bad value for process RSS:\n%s", str(lines))
    raise MemoryException("bad value: %s" % str(lines))

  return {'VmRSS':rss_size_kb, 'VmSize':vsz_kb}

# guarantee that at least VmRSS and VmSize are in the mem_stats
vm_keys = ('VmRSS', 'VmSize') #, 'VmData', 'VmPeak')
def linux_get_memory_usage(pid):
  """
  return dict of memory usage numbers from the procfs entry
  """
  try:
    path = '/proc/%s/status' % pid
    mem_stats = {}
    f = open(path)
    for line in f:
      if line.startswith('Vm'):
        key, value = line.strip().split(':')
        mem_stats[key] = int(value.split()[0].strip())
    f.close()
    for key in vm_keys:
      if key not in mem_stats:
        raise MemoryException('missing key: %s' % key)
    return mem_stats
  except Exception, e:
    raise MemoryException("unexpected error: %s" % e)

if sys.platform == 'linux2':
  get_memory_usage = linux_get_memory_usage
else:
  get_memory_usage = generic_get_memory_usage


# make hotshot/profile/cProfile work the same way by selectively wrapping
# certain classes with a proxy
def get_profiler(profiler_module, path, bias=None):
  if profiler_module == 'cProfile':
    import cProfile
    prof = cProfile.Profile()
    return ProfileProxy(path, prof)
  elif profiler_module == 'cpuprofile':
    import cpuprofile
    prof = cpuprofile.Profile()
    return ProfileProxy(path, prof)

class ProfileProxy(object):
  def __init__(self, filename, profile):
    self.filename = filename
    self.profile = profile

  def runcall(self, *pargs, **kargs):
    return self.profile.runcall(*pargs, **kargs)

  def close(self):
    self.profile.dump_stats(self.filename)
