Download the install source:

```
wget http://msolo.googlecode.com/files/wiseguy-0.5.4.tbz
tar xjvf wiseguy-0.5.4.tbz
```

I tend to use encap, so my `$PREFIX` is frequently something like `/usr/local/encap/wiseguy-x.y.z`, but `/usr/local` is a safe choice.

```
# you might want to change these two variable
BASEDIR="./" 
PREFIX="/usr/local"
cd $BASEDIR/wiseguy-deps/fcgi
./configure --prefix=$PREFIX
make
make install
cd $BASEDIR/wiseguy-deps/py-fastcgi
python ./setup.py build_ext -I$PREFIX/include -L$PREFIX/lib
python ./setup.py install --prefix=$PREFIX
cd $BASEDIR/wiseguy
python ./setup.py build
python ./setup.py install --prefix=$PREFIX
```

I would proceed to the example tutorial.

At this point, you should have all the libraries you need installed. I would try this:

```
wiseguyd --help
```

Hopefully you see:

```
usage: wiseguyd [options]

options:
  -h, --help            show this help message and exit
  --bind-address=BIND_ADDRESS
                        FCGI TCP host:port or unix domain socket path
  --wsgi-app=WSGI_APP   fully qualified symbol that is WSGI compliant
  --management-address=MANAGEMENT_ADDRESS
                        HTTP TCP host:port
  --max-requests=MAX_REQUESTS
                        max requests handled per child
  --max-rss=MAX_RSS     max rss before a child gets a SIGTERM
  --accept-input-timeout=ACCEPT_INPUT_TIMEOUT
                        timeout in seconds between accept() and read()
  --workers=WORKERS     number of worker processes
  --log-level=LOG_LEVEL
                        set the base log level
  --profile-path=PROFILE_PATH
                        log hotshot profile data to this path
  --profile-uri=PROFILE_URI
                        profile any uri matching this regex
  --log-file=LOG_FILE   
  --pid-file=PID_FILE   
```

If Python cannot load libfcgi.so (or some variant) you probably need to rerun ldconfig.

If all went well, I would proceed to the WiseguyExampleTutorial.