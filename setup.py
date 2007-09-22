from distutils.core import setup
import sparrow

setup(
    name="sparrow",
    version=sparrow.version,
    description="text-to-python template language",
    author="Mike Solomon",
    author_email="mas63 @t cornell d0t edu",
    license="BSD-style",
    download_url="",
    platforms=["Posix", "MacOS X", "Windows"],
    classifiers=["Development Status :: 3 - Alpha",
                 "Intended Audience :: Developers",
                 "License :: OSI Approved :: BSD License",
                 "Programming Language :: Python",
                 "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
                 "Topic :: Software Development :: Code Generators",
                 "Topic :: Text Processing",
                 ],
    packages=["sparrow",
              "sparrow.compiler",
              "sparrow.runtime",
              ],
    py_modules=['yappsrt'],
    scripts=["scripts/crunner.py",
             "scripts/sparrow-compile",
             ],
     ) 
