# Introduction #

Wiseguy is a WSGI compliant FastCGI server built on top of python-fastcgi and the Open Market FCGI library. It contains a few patches to deal with various bad behaviors under high load.  In addition to being reasonably fast and low overhead, it contains a number of features that make it well suited for large production sites.


# Installing #

There are three components to wiseguy, so it takes a few moments.  The WiseguyInstallationInstructions list a step-by-step process that should work.


# Example Tutorial #

A small test application is included to make sure the wiseguy installation went well and that you have some hope of running your own.  The WiseguyExampleTutorial should take a few moments to go through.

PN: I've added another sample to the examples. It is a basic routes app. Nothing special, and probably needs work, but you can try it out from the instructions here WiseguyExampleRoutes


# Details #

Wiseguy uses a preforking model where multiple processes answer FCGI requests on a single TCP or Unix domain socket.  It is known to work on Mac OS X and has run happily on a few Linux variants (notably SuSE 10.x and Ubuntu 9.04).

If you need to customize the behavior further, you might want look at WiseguyCallTrace. This explains when certain functions get called which can be otherwise tricky to decipher since the internal implementation is a little fragmented.

The 0.6.x branch of wiseguy includes a forking procedure called "stem cell" - that is documented in WiseguyStemCell.

## Command Line Options ##


--bind-address
> FCGI TCP host:port or unix domain socket path
    * `--bind-address=127.0.0.1:4000`
    * `--bind-address=/var/run/wiseguyd.sock`

--wsgi-app=WSGI\_APP
> fully qualified symbol that is WSGI compliant
> > `--wsgi-app=wiseguy.example.test_app.simple_app`

--management-address

> HTTP TCP host:port
> > `--management-address=127.0.0.1:4001`

--max-requests

> Max requests handled per child. Normally this is unlimited, but for debugging, 1 is a useful option.
> > `--max-requests=1`

--max-rss

> The max memory resident set size (RSS) in kilobyes before a child gets a SIGTERM. This is handy when running in production.
> > `--max-rss=100000` (limit each child to 100MB)

--accept-input-timeout

> Set a timeout in seconds between accept() and read(). This is an approximate antidote to weird condition running behind Apache. If a connection takes longer that this value, the connection is aborted.

--workers
> Set the number of preforked worker processes. Usually a good number to start with is twice the number of physical CPUs. In debug mode, one process is usually good.
> > `--workers=1`

--log-level

> Set the base log level.
> > `--log-level=DEBUG`

--profile-path

> Log hotshot profile data to this path. The can also be done dynamically in the management server.
> > `--profile-path=/tmp/wiseguyd.pstats`

--profile-uri

> Limit profiles to URIs matching this regex
> > `--profile-uri=^/home`

--log-file=LOG\_FILE\_PATH

--pid-file=PID\_FILE\_PATH

## Embedded Admin HTTP Server ##

Right now, wiseguy supports spawning a small HTTP server on a separate port (usually 4001) which can be used for managing the wiseguy daemon.  This is inactive by default, and specifying `--management-address` to `wiseguyd` turns it on. Currently, it only allows connections from localhost.

### Cycle Children ###

This is adds additional options to the usual SIGHUP behavior.

  * `curl "http://localhost:4001/server-cycle?workers=4&skew=2&force=1"`
    * workers - dynamically adjust the number of worker processes
      * (no sanity checking - 32768 would not be a good input)
    * skew - seconds between child kills - prevents machine from cpu spikes caused by restarting interpreters
    * force - send a SIGKILL to actually kill the children

### Profiling CPU Consumption ###

Spawn a new child to collect Hotshot profiling data.

  * `curl "http://localhost:4001/server-profile?request_count=1000&profile_uri=^/home"`
    * request\_count - number of requests to run through the profiler
    * profile\_uri - a regex that indicates if a request should be run through the profiler

If you specify both request\_count and profile\_uri, as in the example, you will collect 1000 executions of servlets matching /home.

### Profiling Memory Consumption ###

Sometimes it is helpful to know when memory is getting consumed at a macro level. This will show up in the wiseguy log file. Note that this will cycle all of the children.

  * `curl "http://localhost:4001/server-profile-memory?enable=1&min_delta=0"`
    * enable - 0 or 1 - toggles memory logging on and off
    * min\_delta - minimum change in memory usage (in kilobytes) that is worth logging


# Current Release #

Trunk is semi-stable, but wiseguy-0.5.4 is production-ready.

  * [wiseguy-0.5.4](http://msolo.googlecode.com/svn/tags/wiseguy-0.5.4)


# Release Notes #

I note most of the progress in the [change log](http://msolo.googlecode.com/svn/trunk/wiseguy/CHANGES).