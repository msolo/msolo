from distutils.core import setup

import spyglass

setup(
  name="spyglass",
  version=spyglass.__version__,
  description="Python application tracing",
  author=spyglass.__author__,
  author_email=spyglass.__author_email__,
  license=spyglass.__license__,
  download_url="",
  platforms=["Posix", "MacOS X", "Windows"],
  classifiers=["Development Status :: 5 - Production/Stable",
               "Intended Audience :: Developers",
               "License :: OSI Approved :: BSD License",
               "Programming Language :: Python",
               "Topic :: Software Development :: Libraries :: Python Modules"],
  packages=["spyglass"],
  ext_package='spyglass',
  ) 
