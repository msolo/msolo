# small test app to make sure we are getting the sockets correctly
from optparse import OptionParser
import sys

op = OptionParser()
op.add_option('--count')

if __name__ == '__main__':
  options, args = op.parse_args()
  print "sys.path", sys.path
  print "server stdout argc", argc
  print >> sys.stderr, "server stderr argv", argv
  print >> sys.stderr, "server options", options.count
  print "stdin", sys.stdin.readline()
