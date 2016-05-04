# Introduction #

Sparrow is a template language heavily inspired by Cheetah. It started out as an experiment to see if techniques from the compiler world were applicable to the mundane details of templates.

At this point, Sparrow works - at least in theory. There are basic tests cases that assure templates are parse, compile, generate and execute correctly. Most language features are covered with a high-level test.


# Details #

The syntax itself is extremely similar to Cheetah, however there are some directives and language features that have been omitted (usually on purpose).  The change log and parser.g file are currently the primary source of information on this, which is not the best. More documentation to come.

Trivial Cheetah templates will probably compile in Sparrow, so that's probably a good place to start.

# Current Release #

This was "current" a while back. Trunk is semi-stable as there as reasonable regression tests.

  * [sparrow-0.5.5](http://msolo.googlecode.com/svn/tags/sparrow-0.5.5)


# Release Notes #

I note most of the progress in the [change log](http://msolo.googlecode.com/svn/trunk/sparrow/CHANGES). The biggest addition is the alternate front end to support an attribute language (think TAL or Kid).

# Performance #

Sparrow has a basic optimizer that can make certain operations much faster. I found a basic 10x1000 table  generation benchmark written by the Genshi team.  I modified it to add Cheetah (my baseline performance target) and Sparrow. This is by no means exhaustive proof that Sparrow is always fast, just that in a simple case of burning through a loop of generating text, it's not too shabby.

```
weaponx:~/Projects/sparrow> python tests/perf/bigtable.py
Genshi tag builder                            967.96 ms
Genshi template                               721.81 ms
Genshi template + tag builder                1029.01 ms
Mako Template                                 240.77 ms
Cheetah template                               56.39 ms
Sparrow template                               59.54 ms
Sparrow template -O1                           53.75 ms
Sparrow template -O2                           15.90 ms
Sparrow template -O3                            9.35 ms

weaponx:~/Projects/sparrow> python                           
Python 2.4.3 (#1, Jan  5 2007, 00:05:16) 
[GCC 4.0.1 (Apple Computer, Inc. build 5367)] on darwin
>>> 
```