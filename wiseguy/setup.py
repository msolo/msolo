from distutils.core import setup


setup(
  name="wiseguy",
  version="0.5.4",
  description="Python WSGI wrapper for py-fastcgi",
  author="Mike Solomon",
  author_email="mas63@cornell.edu",
  license="MIT-style",
  download_url="",
  platforms=["Posix", "MacOS X", "Windows"],
  classifiers=["Development Status :: 5 - Production/Stable",
               "Intended Audience :: Developers",
               "License :: OSI Approved :: MIT License",
               "Programming Language :: Python",
               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
               "Topic :: Software Development :: Libraries :: Python Modules"],
  packages=["wiseguy"],
  ext_package='wiseguy',
  scripts=["scripts/wiseguyd",
           ],
  ) 
