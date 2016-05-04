# wiseguyd and the Python Env #

wiseguy does not install the test applications in the egg it places in site-packages (yay, less fluff), so you're probably running the wiseguyd test command out of the unpacked tarball directory. If, for some reason, your python path does not have "." in it, then wiseguyd won't find the app in it's import.

So, if wiseguyd is returning a 500 when you first fire it up, check your wiseguyd.log (by default in the cwd you ran wiseguyd in). If you see something like:

```
2010-09-15 15:08:03,920 16438 ERROR get_wsgi_app_function test_app.simple_app failed
Traceback (most recent call last):
  File "/usr/local/bin/wiseguyd", line 56, in get_wsgi_app_function
    app_object = __import__(module_name)
ImportError: No module named test_app
```

Or:

```
2010-09-15 15:08:03,923 16438 ERROR error in WSGIRunWrapper
Traceback (most recent call last):
  File "/usr/local/bin/wiseguyd", line 34, in __call__
    for push in self.wsgi_function(environ, start_response):
  File "/usr/local/bin/wiseguyd", line 29, in wsgi_function
    self._wsgi_function = get_wsgi_app_function(self.function_identifier)
  File "/usr/local/bin/wiseguyd", line 62, in get_wsgi_app_function
    raise NoSuchApplication(function_identifier)
NoSuchApplication: test_app.simple_app
```

# Solutions #

If you run:

```
python
> import sys
> print sys.path
```

You'll see what's in your path. If you don't see a full path to the unpacked wiseguy directory, then you have a couple of options. You can temporarily add it to your env with:

```
export PYTHONPATH=/path/to/wiseguy/examples
```

Or, more permanently, you can manually copy the wiseguy samples to you site-packages directory:

```
cp -R /path/to/wiseguy/examples /path/to/python/site-packages/wiseguyexamples
```

In either case, given the above, you'll have to modify the command to wiseguyd a bit:

```
wiseguyd --wsgi-app=test_app.simple_app
```

Should do the trick.