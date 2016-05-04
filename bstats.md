# Exploring Python Profile Data With bstats #


This is a wrapper on the Python stats object to support interactive wandering and exploration of profile data. This might work with stats and cProfile, but it's really only been tested with
output from hotshot on Python 2.4.3

## Download ##

[bstats.py](http://msolo.googlecode.com/svn/trunk/bstats/bstats.py)

## Notes ##

  * `func` usually means a tuple of `(file, line, func_name)` (canonical form)
  * `func` can also be a string, as specially formatted by the underlying stats object

# Profiling Tutorial #

Presuming you have collection some stats data, The basic work flow is this:

```
ipython -i bstats.py

>>> bs = load('plone_view.pstats')
>>> bs = load('plone_view.hotshot')
```

Files can end in '.hotshot', '.prof' or '.pstats' and this function will
compute the stats from raw profiling data if necessary. If you have it, the
.pstats file will be substantially faster to load.

To look at low hanging fruit, sorting by time is a good option:

```
>>> bs.print_top_items(TIME, 10)
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   112200/100    0.777    0.000   20.259    0.203 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:331(interpret)
        98300    0.689    0.000    0.689    0.000 /Plone/3.0/Products/PTProfiler/ProfilerPatch.py:46(_get_name)
        60500    0.645    0.000    3.561    0.000 /Zope/2.10/lib/python/zope/tal/talinterpreter.py:382(do_startTag)
```

This tells you that there is no fruit.

Another approach is to see if some function that returns invariant or
pseudo-static data is getting hit ever call. This sorts by the total time
spent in this function and its callees.

```
>>> bs.print_top_items(CUMULATIVE, 100)
```

This is not always so useful, so I added the FALLOUT sort. This sorts
functions that aren't called often, but result in a lot of cumulative time.
Note that there is now a FALLOUT2 sort - this sorts by the largest amount of
cumulative time per-call which probably returns the 'right' functions more
often.

```
>>> b.print_top_items(FALLOUT, 10)
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        0    0.000             0.000          profile:0(profiler)
        1    0.006    0.006   20.414   20.414 zopectl_hotshot.py:24(x)
       93    0.001    0.000    0.005    0.000 /Plone/3.0/Products/CMFPlone/browser/ploneview.py:187(visibleIdsEnabled)
      100    0.001    0.000   20.408    0.204 /Plone/3.0/Products/CMFPlone/Portal.py:114(view)
      100    0.003    0.000   20.407    0.204 /Plone/3.0/Products/CMFDynamicViewFTI/browserdefault.py:89(__call__)
```

Discard the first 2-3 lines - they are the stats collection process.

The next lines are pretty obvious too, so again, not super helpful. We did 100
web hits, so these things got run 100 times.

Adding a restriction on call count, we can see things that got executed twice
per web hit (probably).

```
>>> b.print_top_items(FALLOUT, 10, b.call_count_filter(200))
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      200    0.006    0.000    7.488    0.037 /Plone/3.0/lib/python/plone/portlets/manager.py:63(render)
      200    0.020    0.000    1.048    0.005 /Plone/3.0/Products/ResourceRegistries/tools/BaseRegistry.py:750(getEvaluatedResources)
      200    0.004    0.000    0.108    0.001 /Plone/3.0/Products/CMFCalendar/CalendarTool.py:347(getBeginAndEndTimes)
```

This is slightly interesting - this looks like 35% of execution time comes
from one particular function getting called twice per hit. To dig a little
deeper, you can run these:

To show how this function got called:
```
>>> b.print_func_callers('/Plone/3.0/lib/python/plone/portlets/manager.py:63(render)')
        ncalls  tottime  percall  cumtime  percall filename:lineno(function)
[  200] 1500/1200    0.034    0.000   11.232    0.009 /Users/limi/Projects/Zope/2.10/lib/python/Products/Five/browser/providerexpression.py:13(__call__)
```

To show what functions this function calls:
```
>>> b.print_func_callees('/Plone/3.0/lib/python/plone/portlets/manager.py:63(render)')
      ncalls  tottime  percall  cumtime  percall filename:lineno(function)
[  200]  2000/100    0.011    0.000   20.389    0.204 /Zope/2.10/lib/python/Shared/DC/Scripts/Bindings.py:311(__call__)
[  200]       700    0.000    0.000    0.000    0.000 /Zope/2.10/lib/python/OFS/SimpleItem.py:338(__len__)
[  200]       600    0.002    0.000    0.071    0.000 /Plone/3.0/lib/python/plone/portlets/manager.py:55(portletsToShow)
```

Another function that can have some limited utility is
`print_common_call_chain` - this tries to guess at the most common way the given
function was called.  It can make mistakes, and it will just bail on recursive
functions, but occasionally I find it useful.

```
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
```

