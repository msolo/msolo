from math import exp, log
from time import time

"""Exponential Decay Stats

This module keeps a series of counters that efficiently track historical rates
over different time intervals.
"""

__author__ = "Palash Nandy"

class ExpDecayCounter(object):
  # to increase X by n, we do this:
  # X <- X*exp(-lambda * del_t) + n * (1 - exp(-lambda*del_t))
  #
  # So to calculate half life:
  # exp(-lambda * T) = 1/2
  # -lamda * T = ln (1/2)
  # lambda = -ln(1/2) / T
  #
  # To use the counter to do rates instead of just average, set the period
  # to the rate period. Eg. to know the average rate per second over a 1 minute
  # interval use, period = 1 and half_life = 12
  def __init__(self, half_life, last_update=None, init=0, period=None):
    self.half_life = half_life
    self.last_update = last_update
    if self.last_update is None:
      self.last_update = time()
    self.x = init
    self.decay_const = - log(0.5) / self.half_life
    self.period = period
    
  def update(self, n, update_time=None):
    if update_time is None:
      update_time = time()
      
    del_t = update_time - self.last_update
    weight_fraction = self._get_weight_fraction(del_t)
    update_fraction = 1 - weight_fraction

    # if we have specified a period, that is to say, we want to know
    # how many widgets happened per second, then the update decay
    # is dependent on the period
    if self.period is not None:
      update_fraction = 1 - self._get_weight_fraction(self.period)
      
    self.x = (self.x * weight_fraction) + (n * update_fraction)
    self.last_update = update_time


  def _get_weight_fraction(self, del_t):
    return exp(-1 * self.decay_const * del_t)

  def get_value(self,  time_now=None):
    if time_now is None:
      time_now = time()
    del_t = time_now - self.last_update
    weight_fraction = self._get_weight_fraction(del_t)
    return self.x * weight_fraction

  value = property(get_value, None, None, 'Current decayed value of counter')

  def __repr__(self):
    del_t = time() - self.last_update
    return '%.2f [state: %.2f %d secs ago (l:%d)]' % (
      self.value, self.x, int(del_t), self.half_life)


# some presests
# roughly - 1min, 5min, 15min moving averages
fast_decays = (12, 60, 180)
# roughly - 1min, half an hour, 6 hours, 1 day, 7 days
slow_decays = (12, 720, 4320, 17280, 120960)


class MultiExpDecayCounter(object):
  """A wrapper around ExpDecayCounter to store a list of counters.

  Normally we are intrested in the same variable with several half lives."""
  def __init__(self, half_life_list, last_update=None, init=0, period=None):
    self.counters = [ExpDecayCounter(half_life, last_update, init, period)
                     for half_life in half_life_list]

  def update(self, n, update_time=None):
    for counter in self.counters:
      counter.update(n, update_time)

  def get_values(self, time_now=None):
    return [x.get_value(time_now) for x in self.counters]

  values = property(get_values, None, None, 'current decayed value of all counters')

  def __repr__(self):
    return '\n'.join([x.__repr__() for x in self.counters])





# if a single event happens, at what decay constant does the average after time t over t
# equal the exponential decay
#  N*exp(-lambda * t) = N/t
#  -lambda * t = ln(1/t)
# lambda = - ln(1/t) / t
# lambda = ln(t) / t

