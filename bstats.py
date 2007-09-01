import os.path
import pstats
import re

from itertools import imap

__author__ = 'Mike Solomon <mas63 @t cornell d0t edu>'
__version__ = '0.2'
__license__ = 'BSD License'

# pcalls - primitive calls, no recursive calls are counted
# time - probably the most useful by default
# fallout2 - sort by cumulative time per call
CALL_COUNT = 'calls'
PCALL_COUNT = 'pcalls'
CUMULATIVE = 'cumulative'
TIME = 'time'
FALLOUT = 'fallout'
FALLOUT2 = 'fallout2'


"""
this is a wrapper on the python stats object to support interactive wandering
and exploration of profile data

func usually means a tuple of file, line, func_name (canonical form)
it can also be a string, as specially formatted by the underlying stats object

this might work with stats and cProfile, but it's really only been tested with
output from hotshot on python 2.4.3

Presuming you've collected raw hotshot data and built a pstats object, you can
save this file:

stats.dump_stats('plone_view.pstats')

Once you have that data, you can ship it around to friends and it should be
pretty small and dense. The basic work flow is this:

ipython -i bstats.py

>>> bs = load('plone_view.pstats')
>>> bs = load('plone_view.hotshot')

Files can end in '.hotshot', '.prof' or '.pstats' and this function will
compute the stats from raw profiling data if necessary. If you have it, the
.pstats file will be substantially faster to load.


To look at low hanging fruit, sorting by time is a good option:

>>> b.print_top_items(TIME, 10)
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   112200/100    0.777    0.000   20.259    0.203 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:331(interpret)
        98300    0.689    0.000    0.689    0.000 /Plone/3.0/Products/PTProfiler/ProfilerPatch.py:46(_get_name)
        60500    0.645    0.000    3.561    0.000 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:382(do_startTag)

This tells you that there is no fruit.

Another approach is to see if some function that returns invariant or
pseudo-static data is getting hit ever call. This sorts by the total time
spent in this function and its callees.

>>> b.print_top_items(CUMULATIVE, 100)

This is not always so useful, so I added the FALLOUT sort. This sorts
functions that aren't called often, but result in a lot of cumulative time.
Note that there is now a FALLOUT2 sort - this sorts by the largest amount of
cumulative time per-call which probably returns the 'right' functions more
often.

>>> b.print_top_items(FALLOUT, 10)
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        0    0.000             0.000          profile:0(profiler)
        1    0.006    0.006   20.414   20.414 zopectl_hotshot.py:24(x)
       93    0.001    0.000    0.005    0.000 /Plone/3.0/Products/CMFPlone/browser/ploneview.py:187(visibleIdsEnabled)
      100    0.001    0.000   20.408    0.204 /Plone/3.0/Products/CMFPlone/Portal.py:114(view)
      100    0.003    0.000   20.407    0.204 /Plone/3.0/Products/CMFDynamicViewFTI/browserdefault.py:89(__call__)

The discard the first 2-3 lines - they are the stats collection process.

The next lines are pretty obvious too, so again, not super helpful. We did 100
web hits, so these things got run 100 time.

Adding a restriction on call count, we can see things that got executed twice
per web hit (probably).

>>> b.print_top_items(FALLOUT, 10, b.call_count_filter(200))
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      200    0.006    0.000    7.488    0.037 /Plone/3.0/lib/python/plone/portlets/manager.py:63(render)
      200    0.020    0.000    1.048    0.005 /Plone/3.0/Products/ResourceRegistries/tools/BaseRegistry.py:750(getEvaluatedResources)
      200    0.004    0.000    0.108    0.001 /Plone/3.0/Products/CMFCalendar/CalendarTool.py:347(getBeginAndEndTimes)

This is slightly interesting - this looks like 35% of execution time comes
from one particular function getting called twice per hit. To dig a little
deeper, you can run these:

show how this function got called:
>>> b.print_func_callers('/Plone/3.0/lib/python/plone/portlets/manager.py:63(render)')
        ncalls  tottime  percall  cumtime  percall filename:lineno(function)
[  200] 1500/1200    0.034    0.000   11.232    0.009 /Users/limi/Projects/Zope/2.10/lib/python/Products/Five/browser/providerexpression.py:13(__call__)

show what functions this function calls:
>>> b.print_func_callees('/Plone/3.0/lib/python/plone/portlets/manager.py:63(render)')
      ncalls  tottime  percall  cumtime  percall filename:lineno(function)
[  200]  2000/100    0.011    0.000   20.389    0.204 /Zope/2.10/lib/python/Shared/DC/Scripts/Bindings.py:311(__call__)
[  200]       700    0.000    0.000    0.000    0.000 /Zope/2.10/lib/python/OFS/SimpleItem.py:338(__len__)
[  200]       600    0.002    0.000    0.071    0.000 /Plone/3.0/lib/python/plone/portlets/manager.py:55(portletsToShow)

Another function that can have some limited utility is
print_common_call_chain - this tries to guess at the most common way the given
function was called.  It can make mistakes, and it will just bail on recursive
functions, but occaisionally I find it useful.

>>> b.print_common_call_chain('/Zope/2.10/lib/python/Shared/DC/Scripts/Bindings.py:311(__call__)', 10)
         ncalls  tottime  percall  cumtime  percall filename:lineno(function)
[ 2000]  2000/100    0.011    0.000   20.389    0.204 /Zope/2.10/lib/python/Shared/DC/Scripts/Bindings.py:311(__call__)
[  600]  1200/900    0.019    0.000    3.250    0.004 /Zope/2.10/lib/python/zope/viewlet/manager.py:106(render)
[ 1200] 1500/1200    0.034    0.000   11.232    0.009 /Zope/2.10/lib/python/Products/Five/browser/providerexpression.py:13(__call__)
[ 1500] 106000/36600    0.342    0.000   16.669    0.000 /Zope/2.10/lib/python/zope/tales/tales.py:691(evaluate)
[33600] 33600/25000    0.102    0.000    1.097    0.000 /Zope/2.10/lib/python/Products/PageTemplates/Expressions.py:185(evaluateBoolean)
[24500] 24500/4900    0.064    0.000   13.513    0.003 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:853(do_condition)
[24500] 112200/100    0.777    0.000   20.259    0.203 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:331(interpret)
[77800] 38900/100    0.255    0.000   20.215    0.202 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:510(no_tag)
[32500] 32900/100    0.138    0.000   20.215    0.202 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:518(do_optTag)
[32900] 39300/100    0.088    0.000   20.216    0.202 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:530(do_optTag_tal)
"""

pstats.Stats.sort_arg_dict_default['fallout'] = (
  ((1, 1), (3,-1)), "fallout function")

class BrowseableStats(pstats.Stats):		
 	def get_top_items(self, sort_key, count, filter_function=None):
		self.sort_stats(sort_key)
		if filter_function:
			return filter_function(self.fcn_list)[:count]
		return self.fcn_list[:count]

	# return a list of calling functions
	# sorted by descending call counts
	def get_func_caller_counts(self, func):
		func = convert_function(func)
		try:
			(primitive_call_count, total_call_count, total_time, cumulative_time,
			 caller_dict) = self.stats[func]
			callers = sorted([
				(call_count, caller_func)
				for caller_func, call_count in caller_dict.iteritems()], reverse=True)
			return [(x[1], x[0]) for x in callers]
		except KeyError, e:
			raise

	# return a list of called functions
	# sorted by descending call counts
	def get_func_callee_counts(self, func):
		func = convert_function(func)
		self.calc_callees()
		try:
			callee_dict = self.all_callees[func]
			callees = sorted([
				(call_count, caller_func)
				for caller_func, call_count in callee_dict.iteritems()], reverse=True)
			return [(x[1], x[0]) for x in callees]
		except KeyError, e:
			raise

	def get_common_call_chain(self, func, max_depth=20):
		func = convert_function(func)
		(primitive_call_count, total_call_count, total_time, cumulative_time,
		 caller_dict) = self.stats[func]
		call_chain = [(func, total_call_count)]
		max_depth -= 1
		while max_depth:
			most_common_caller = self.get_func_caller_counts(call_chain[-1][0])[0]
			if most_common_caller in call_chain:
				raise Exception("recursive call detected: %s" % most_common_caller)
			call_chain.append(most_common_caller)
			max_depth -= 1

		return call_chain

	def print_func_list(self, func_list):
		self.print_title()
		for f in func_list:
			self.print_line(f)

	def print_top_items(self, sort_key, count, filter_func=None):
		self.print_func_list(self.get_top_items(sort_key, count, filter_func))

	def print_func_callers(self, func):
		self.print_func_caller_list(self.get_func_caller_counts(func))

	def print_func_callees(self, func):
		self.print_func_caller_list(self.get_func_callee_counts(func))

	def print_func_caller_list(self, func_list):
		print ' ' * 8,
		self.print_title()
		for caller_func, caller_count in func_list:
			print '[%5s]' % caller_count,
			self.print_line(caller_func)

	def print_common_call_chain(self, func, max_depth=20):
		self.print_func_caller_list(self.get_common_call_chain(func, max_depth))

  # build a dictionary of function stats (mostly for printing)
	def func_stats(self, func):
		d = {}
		cc, nc, tt, ct, callers = self.stats[func]
		c = str(nc)
		if nc != cc:
			c = c + '/' + str(cc)
			d['rcalls'] = cc
		else:
			d['rcalls'] = ''
			
		d['call_str'] = c
		d['ncalls'] = nc
		d['tottime'] = tt
		try:
			d['percall'] = tt/nc
		except ZeroDivisionError:
			d['percall'] = 'inf'
			
		d['cumtime'] = ct
		try:
			d['cumpercall'] = ct/cc
		except ZeroDivisionError:
			d['cumpercall'] = 'inf'
			
		d['func_name'] = pstats.func_std_string(func)
		return d

	def call_count_filter(self, call_count):
		def filter_function(function_list):
			results = []
			for func in function_list:
				stats = self.func_stats(func)
				if stats['ncalls'] == call_count:
					results.append(func)
			return results
		return filter_function
  
	def sort_stats(self, *field):
		if field[0] == FALLOUT2:
			return self.fallout2_sort_stats()
		else:
			return pstats.Stats.sort_stats(self, *field)

	# sort by the largest amount of cumulative time spent per-call
	def fallout2_sort_stats(self):
		stats_list = []
		for func, (cc, nc, tt, ct, callers) in self.stats.iteritems():
			cumulative_percall = 0
			if cc != 0:
				cumulative_percall = ct / cc
			stats_list.append((cumulative_percall, func))

		stats_list.sort(reverse=True)

		self.fcn_list = [fcn_tuple[-1] for fcn_tuple in stats_list]
		return self

	
# this will parse a string into the bits for a function tuple
func_pattern = re.compile('(.*):(\d+)\((.*)\)')

# function string to function tuple
# handy when you are reading through a stack and want to get info about
# a function - you can just copy/paste this
def fs2ft(s):
	file, line, fname = func_pattern.match(s).groups()
	return file, int(line), fname

# convert a function string to tuple if necessary
def convert_function(func):
	if isinstance(func, str):
		return fs2ft(func)
	return func


# load stats data from either raw profiling info, or a marshaled pstats file
def load(filename):
	path, ext = os.path.splitext(filename)
	if ext in ('.prof', '.hotshot'):
		return load_hotshot_profile(filename)
	elif ext in ('.pstats',):
		return BrowseableStats(filename)

	raise Exception("unknown file extention: '%s'" % ext)
	
def load_hotshot_profile(filename):
	import hotshot.stats
	stats = hotshot.stats.load(filename)
	pstats_path = os.path.splitext(filename)[0] + '.pstats'
	stats.dump_stats(pstats_path)
	bs = BrowseableStats(pstats_path)
	return bs
