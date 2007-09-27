from distutils.core import setup

import sparrow

setup(
    name="sparrow",
    version=sparrow.__version__,
    description="text-to-python template language",
    author=sparrow.__author__,
    author_email=sparrow.__author_email__,
    license=sparrow.__license__,
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
