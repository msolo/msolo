# Introduction #

Many apps I've worked on rely heavily on network services - MySQL, RPC servers, memcache, etc.

Often times, a slow service can cause the whole application to bog down. This tool just automates some actions you could perform by hand to make it easier to find the problematic service.

## Disclaimer ##
This works only on Linux at this point, as it is just wrapping `lsof` and `strace`. It's also fairly resource intensive for reasons I don't quite understand. If your application uses a lot of short-lived file descriptors, this probably isn't going to help you a lot, since `lsof` will probably be unable to reliably determine the service represented by a given file descriptor over a period of time.

# Usage #

The simplest usage:

`svncstat -p <pid>`

There are other options (-h is a good one).

It outputs 4 columns:
  1. fd/name - the file descriptor, or the name it resolved to, if available
  1. average + 1 standard deviation call duration in milliseconds
  1. total time spent on this service / fd
  1. total number of system calls observed on this service / fd

The rows are sorted by total time spent on this service.

```
[mike]weaponx:~> sudo svcstat -p 32633
fd <name> avg+std_dev (ms) total count
unknown 6      35.508  1244.257   747
rpc4:80        20.474   204.741    10
db1:3306        3.420   157.050   666
db3:3306        2.240   131.298   538
db5:3306        1.164    76.597   492
unknown 40      9.050    37.186    16
/dev/urandom    3.464    33.559    80
memcache2:11211 0.656    23.264   172
memcache3:11211 0.410    13.957   104
memcache1:11211 0.455    12.303   100
```


