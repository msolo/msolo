from distutils.core import setup

import wiseguy

setup(
  name="wiseguy",
  version=wiseguy.__version__,
  description="Python WSGI wrapper for py-fastcgi",
  author=wiseguy.__author__,
  author_email=wiseguy.__author_email__,
  license=wiseguy.__license__,
  download_url="",
  platforms=["Posix", "MacOS X", "Windows"],
  classifiers=["Development Status :: 5 - Production/Stable",
               "Intended Audience :: Developers",
               "License :: OSI Approved :: BSD License",
               "Programming Language :: Python",
               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
               "Topic :: Software Development :: Libraries :: Python Modules"],
  packages=["wiseguy"],
  ext_package='wiseguy',
  scripts=["scripts/wiseguyd",
           ],
  )
