# Prerequisites #

I use lighttpd-1.4.x in this example.  Any FastCGI compatible web server should work, but the configuration will vary dramatically.  It should be pretty painless to get lighttpd up and running, so that's why I chose it.

# Running An App With wiseguyd #

Go ahead and edit `config/lighttpd-wiseguy.conf` - change the `logbase` and `docbase` variables at the top of the file to something reasonable for your system. Then try to start lighttpd on port 8000:

```
lighttpd -D -f lighttpd-wiseguy.conf
```

You should be able to see some sort of directory listing for the files in `docbase` if you do this:

```
curl -i http://localhost:8000/
```

Now you need to tell `wiseguyd` to run the test application.

```
wiseguyd --wsgi-app=wiseguy.examples.test_app.simple_app
```

Hopefully all goes well - no errors and whatnot. Now test that `lighttpd` can talk to `wiseguyd`.

```
curl -i "http://localhost:8000/wiseguy"
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 20
Date: Sat, 17 May 2008 21:09:56 GMT
Server: lighttpd/1.4.15

Hello from Wiseguy!
```

Great success!  (If not, check this WiseguyEnv)

If you want to check the environment wiseguy provides, you can run this:

```
curl -i "http://localhost:8000/wiseguy/env"
HTTP/1.1 200 OK
Connection: close
Content-type: text/plain
Content-length: 977
Date: Sat, 17 May 2008 21:13:25 GMT
Server: lighttpd/1.4.15

{'DOCUMENT_ROOT': '/Users/mike/Sites',
 'FCGI_ROLE': 'RESPONDER',
 'GATEWAY_INTERFACE': 'CGI/1.1',
 'HTTP_ACCEPT': '*/*',
 'HTTP_HOST': 'localhost:8000',
 'HTTP_USER_AGENT': 'curl/7.16.4 (i386-apple-darwin8.10.1) libcurl/7.16.4 zlib/1.2.3',
 'PATH_INFO': '/env',
 'PATH_TRANSLATED': '/Users/mike/Sites/env',
 'QUERY_STRING': '',
 'REDIRECT_STATUS': '200',
 'REMOTE_ADDR': '127.0.0.1',
 'REMOTE_PORT': '49357',
 'REQUEST_METHOD': 'GET',
 'REQUEST_URI': '/wiseguy/env',
 'SCRIPT_FILENAME': '/Users/mike/Sites/wiseguy',
 'SCRIPT_NAME': '/wiseguy',
 'SERVER_ADDR': '127.0.0.1',
 'SERVER_NAME': 'localhost:8000',
 'SERVER_PORT': '8000',
 'SERVER_PROTOCOL': 'HTTP/1.1',
 'SERVER_SOFTWARE': 'lighttpd/1.4.15',
 'wiseguy.start_time': 1211058805.9881599,
 'wsgi.errors': <fcgi.Stream object at 0x41140>,
 'wsgi.input': <fcgi.Stream object at 0x41160>,
 'wsgi.multiprocess': True,
 'wsgi.multithread': False,
 'wsgi.run_once': False,
 'wsgi.url_scheme': 'http',
 'wsgi.version': (1, 0)}
```