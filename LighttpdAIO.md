# Intro #

lighttpd-aio is a set of changes to serve small images very quickly - even if the disks underneath are under heavy load.  It does this by approximating asynchronous disk io with pthreads - there are more details below.

This was written over the course of a few days a couple of years back. This was the first time I had ever looked at the lighty source code, so it's not pretty.

This document will quickly outline the good, the bad and the ugly as well as provide some documentation for the few config vars that can tune this code.


# Performance and Stability #

This has been used successfully for more than a year.

My setup:
  * dual-core Opteron 270
  * 2 2 x 250GB SATA RAID1 volumes
  * SuSE 10.1 64-bit
  * Reiser3, noatime, 80% avg utilization as reported by iostat
  * 2 workers, 6 disk threads per worker
  * 8700 http req/s
  * 300 days of process uptime
  * ~200MB memory footprint of for each lighttpd instance

Your mileage may vary. :-)


# Overall Design #

The basic idea is that popular content should be cached and served instantly while random requests that must wait for disk io should happen out of the main event loop to prevent 'stalling'.

This patch can be more accurately described as 'asynchronous prefetch'.  The core event loop in lighty has a new state to reflect waiting for data.  There is a disk io request queue (prefetcher.c) that gets drained by the io threads.  Files are mmap'd and read entirely into memory before being returned to the completion queue.  The completed io requests are communicated via the stat cache, which is ugly. (mod\_prefetch.c)


# Limitations #

A missing file (404) is not handled asynchronously, so a lot of hits to non-existant files can reduce performance.

Since files are read completely into memory, it makes it somewhat unsuitable for very large requests. I used this for serving 4-40KB files.

The queues drain disk items one at a time, so there is more futex()'ing than is really necessary.

Adjusting the size of the stat cache results in a lot more memory allocating and cpu to do the stale sweeping. I'm not sure that a splay tree is really the right data structure for this.

This has only been extensively tested on Linux (SuSE 10.1 64-bit). It compiles and seems to run on my MacBook.

# Download #

  * [lighttpd-aio-1.4.11.8.tbz](http://msolo.googlecode.com/files/lighttpd-aio-1.4.11.8.tbz)

# Compiling #

Using pthreads, you probably want reentrant things. I also 'need' gnu99 since I'm lazy.

```
./configure CFLAGS='-g -D_POSIX_REENTRANT_FUNCTIONS -DREENTRANT -std=gnu99'
```

# Config File Options #

server.errorfile : a specific file to return on 404, including an image files. (default = '')

prefetch.thread\_count : the number of threads used to fetch file from disk.  (default = 4)

prefetch.queue\_size : the max number of outstanding disk requests - further requests result in a 503. (default = 1024)

prefetch.stat\_cache\_stale\_timeout : the number of seconds for a stat entry will be considered stale. (default = 2 )

prefetch.stat\_cache\_missing\_file\_timeout : the number of seconds to negatively cache a missing file. 0 means it will cache it indefinitely - until it is otherwise evicted from the stat cache. (default = 0)

prefetch.error\_file - a specific file to return on a 503 (default = '')


# Sample Config File #
```
server.modules = (
        "mod_access",
        "mod_alias",
        "mod_prefetch",
)


server.event-handler = "linux-sysepoll"

mimetype.assign             = (
        ".jpg"          =>      "image/jpeg",
        ".gif"          =>      "image/gif",
 )

prefetch.thread_count = 6
prefetch.stat_cache_stale_timeout = 60
prefetch.stat_cache_missing_file_timeout = 60
prefetch.queue_size = 4096
prefetch.error_file = "/web/htdocs/img/503.gif"

server.network-backend = "writev"
server.errorfile = "/web/htdocs/img/404.jpg"

server.max-keep-alive-requests = 4
server.max-keep-alive-idle = 4

# server.max-worker is only supported in relases >= 1.4.11.8
server.max-worker = 2
```