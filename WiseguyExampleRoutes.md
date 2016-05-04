# Prerequisites #

If you haven't already, proceed to start up lighttpd as outlined on the WiseguyExampleTutorial


Now you need to tell `wiseguyd` to run the test application.

```
wiseguyd --wsgi-app=wiseguy.examples.routes.routes.app
```

Once again, hopefully all went well. If there was a problem, most likely it's that the examples directory is not installed in wiseguy. Check out WiseguyEnv to be sure.

# Testing Routes #

There are a few things you can try:

1) ` curl -i http://localhost:8000/wiseguy `

```
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 17
Date: Mon, 19 May 2008 23:49:13 GMT
Server: lighttpd/1.4.18

This is the index
```


2) ` curl -i http://localhost:8000/wiseguy/hello `

```
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 11
Date: Mon, 19 May 2008 23:51:39 GMT
Server: lighttpd/1.4.18

Hello world
```


3) ` curl -i http://localhost:8000/wiseguy/hello?name=FooBar `

```
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 11
Date: Mon, 19 May 2008 23:51:39 GMT
Server: lighttpd/1.4.18

Hello FooBar
```


4) ` curl -i http://localhost:8000/wiseguy/GarbageURL `

```
HTTP/1.1 404 Not Found
Content-type: text/plain
Content-length: 27
Date: Mon, 19 May 2008 23:53:00 GMT
Server: lighttpd/1.4.18

404 This page was not found
```


That's it for now. I plan on making a RegExRoutes class next, so you can do magical things, such as routing /2008/05 to /archive and have that page parse the year and month (which seems to be the most common test for a routing app :)

I also need to securify the module loading, so people can't be as evil as they can right now probably.