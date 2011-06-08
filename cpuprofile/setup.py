from distutils.core import setup, Extension

setup(
  name="cpuprofile",
  version="1.0",
  py_modules=['cpuprofile'],
  ext_modules=[
    Extension(
      "_cpuprof",
      sources=["_lsprof.c", "rotatingtree.c"]
    )
  ]
)

