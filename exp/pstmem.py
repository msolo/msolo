#!/usr/bin/env python

import sys

# guarantee that at least VmRSS and VmSize are in the mem_stats
vm_keys = ('VmRSS', 'VmSize') #, 'VmData', 'VmPeak')
def get_memory_usage(pid):
  """
  return dict of memory usage numbers from the procfs entry
  """
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

  shared, private, swap = get_smaps_memory(pid)
  mem_stats['shared'] = shared
  mem_stats['private'] = private
  mem_stats['swap'] = swap

  return mem_stats

def get_smaps_memory(pid):
  """Returns (shared_memory, private_memory) in kb"""
  smaps_file = open('/proc/%s/smaps' % pid)
  private_mem = 0
  shared_mem = 0
  swap_mem = 0
  for line in smaps_file:
    if line[:7] == 'Private':
      # line =~ 'Private_Dirty:        12 kB'
      # hope it's always 'kB'
      _, value, unit = line.split()
      private_mem += int(value)
    elif line[:6] == 'Shared':
      _, value, unit = line.split()
      shared_mem += int(value)
    elif line[:5] == 'Swap:':
      _, value, unit = line.split()
      swap_mem += int(value)
  return shared_mem, private_mem, swap_mem

# Estimate the amount of RAM occupied by a process tree.
# This involved discounting segments shared across processes.
# In reality, these processes need not have any inheritence relationship, but
# you would have to read smaps more completely and compute the intersection of
# all shared segments. Here we make some assumptions that a generally true
# for forked workers.
def pst_mem(pid):
  pid_list = open('/proc/%s/task/%s/children' % (pid, pid)).read().strip().split()
  pid_list.append(pid)

  mem_usage = []
  for pid in pid_list:
    mem_usage.append(get_memory_usage(pid))

  # we assume swap is private (there is no way to find the
  # shared component of swap)
  total_private_mem = sum(mem['private'] + mem['swap']
                          for mem in mem_usage)
  max_shared_mem = max(mem['shared'] for mem in mem_usage)
  total_in_use = max_shared_mem + total_private_mem
  return {'PrivSize': total_private_mem, 'MaxSharedSize': max_shared_mem, 'TotalInUse': total_in_use}

if __name__ == '__main__':
  print pst_mem(sys.argv[1])
