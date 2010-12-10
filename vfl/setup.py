from distutils.core import setup

import vfl

setup(name="vfl",
      version=vfl.__version__,
      description="versioned file layout",
      author=vfl.__author__,
      author_email=vfl.__author_email__,
      license=vfl.__license__,
      download_url="",
      platforms=["Posix", "MacOS X"],
      classifiers=["Development Status :: 5 - Production/Stable",
                   "Intended Audience :: Developers",
                   "License :: OSI Approved :: %s" % vfl.__license__,
                   "Programming Language :: Python",
                   "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
                   "Topic :: Software Development :: Libraries :: Python Modules"],
      py_modules=["vfl"],
      scripts=["scripts/vflmake",
               "scripts/vflsquish",
               ],
     ) 
