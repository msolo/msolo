import hotshot.log
import hotshot.stats
import profile
import pstats


from hotshot.log import ENTER, EXIT
from hotshot.stats import Profile, _brokentimer

default_io_functions = [
    ('socket.py', 272, 'read'),
    ('socket.py', 315, 'readline'),
    ('smtplib.py', 311, 'send'),
    ('threading.py', 195, 'wait'),
    ('httplib.py', 642, 'send'),
    ('memcache.py', None, 'send_cmd'),
    ('MySQLdb/cursors.py', None, '_do_query'),
    ('MySQLdb/cursors.py', None, '_query'),
    ('MySQLdb/cursors.py', None, '_do_get_result'),
#    ('test_io.py', 10, 'fake_io'),
]


# try to remove io delays from the profiling equation
class StatsLoader(hotshot.stats.StatsLoader):
  def load(self, io_functions=(), function_normalizer=None):
    if function_normalizer is not None:
      io_functions = set([function_normalizer(f) for f in io_functions])

    # print 'io_functions', io_functions

    # The timer selected by the profiler should never be used, so make
    # sure it doesn't work:
    p = Profile()
    p.get_time = _brokentimer
    log = hotshot.log.LogReader(self._logfn)
    taccum = 0
    for event in log:
      what, (filename, lineno, funcname), tdelta = event
      function_signature = (filename, lineno, funcname)
      if function_normalizer is not None:
        function_signature = function_normalizer(function_signature)
        # print 'function_signature', function_signature

      if function_signature in io_functions:
        # print "found io function", function_signature
        tdelta = 0
      
      if tdelta > 0:
        taccum += tdelta

      # We multiply taccum to convert from the microseconds we
      # have to the seconds that the profile/pstats module work
      # with; this allows the numbers to have some basis in
      # reality (ignoring calibration issues for now).

      if what == ENTER:
        frame = self.new_frame(filename, lineno, funcname)
        p.trace_dispatch_call(frame, taccum * .000001)
        taccum = 0

      elif what == EXIT:
        frame = self.pop_frame()
        p.trace_dispatch_return(frame, taccum * .000001)
        taccum = 0


    assert not self._stack
    return pstats.Stats(p)


#import psyco
#psyco.bind(StatsLoader.load)
