#!/usr/bin/env python

import imp
import os.path
import sys

from pprint import pprint

import sparrow.compiler.parser
import sparrow.compiler.scanner
import sparrow.compiler.analyzer
analyzer = sparrow.compiler.analyzer

import sparrow.compiler.codegen
import sparrow.runtime.runner


def print_tree_walk(node, indent=0):
  if indent > 5:
    raise 'error'
  print '%s%s' % (' ' * indent, node)
  for n in node.child_nodes:
    print_tree_walk(n, indent + 1)

def parse(rule, text):
  parser = sparrow.compiler.parser.SparrowParser(
    sparrow.compiler.scanner.SparrowScanner(text))
  return sparrow.compiler.parser.wrap_error_reporter(parser, rule)

def process_file(filename, options):
  print_lines = []
  def print_output(*args):
    if options.quiet:
      print_lines.append(args)
    else:
      print >> sys.stderr, ' '.join(args)

  opt = analyzer.optimizer_map[options.optimizer_level]
  opt.update(collapse_optional_whitespace=options.ignore_optional_whitespace)

  classname = sparrow.compiler.analyzer.filename2classname(filename)
  try:
    print_output("compile", filename)
    f = open(filename, 'r')
    source_data = f.read().decode('utf8')
    parse_root = parse('goal', source_data)

    if not options.quiet:
      #print "parse_root"
      #pprint(parse_root)
      print "parse_root walk"
      print_tree_walk(parse_root)

    ast_root = sparrow.compiler.analyzer.SemanticAnalyzer(
      filename, parse_root, opt).get_ast()
    
    if not options.quiet:
      #print "ast_root"
      #pprint(ast_root)
      print "ast_root walk"
      print_tree_walk(ast_root)

    if not options.quiet:
      print "generate python code"

    code_generator = sparrow.compiler.codegen.CodeGenerator(ast_root)

    src_code = code_generator.get_code()
    if not options.quiet:
      print "src_code"
      for i, line in enumerate(src_code.split('\n')):
        print '% 3s' % (i + 1), line
  except Exception, e:
    print >> sys.stderr, "FAILED:", classname, e
    raise

  if options.test:

    #print >> sys.stderr, "test", classname, '...',
    print_output("test", classname, '...')

    test_module_filename = 't.py'
    module_file = open(test_module_filename, 'w')
    module_file.write(src_code)
    module_file.close()
    module_file = open(test_module_filename, 'r')

    try:
      imp.load_source(classname, test_module_filename, module_file)
    except Exception, e:
      current_output = str(e)
      raised_exception = True
      print >> sys.stderr, "FAILED:", classname, current_output
      raise
      
    module_file.close()
    try:
      os.remove(test_module_filename)
    except OSError, e:
      print >> sys.stderr, "ERROR:", e
    try:
      os.remove(test_module_filename + 'c')
    except OSError, e:
      print >> sys.stderr, "ERROR:", e

    if options.test_input:
      search_list = [
        sparrow.runtime.runner.load_search_list(options.test_input)]
    else:
      search_list = []
      
    raised_exception = False
    try:
      class_object = getattr(__import__(classname), classname)
      template = class_object(search_list=search_list)
      current_output = template.main().encode('utf8')
    except Exception, e:
      current_output = str(e)
      raised_exception = True

    test_output_path = os.path.join(os.path.dirname(filename),
                    options.test_output,
                    classname + '.txt')

    if options.accept_test_result:
      test_file = open(test_output_path, 'w')
      test_file.write(current_output)
      test_file.close()
      
    try:
      test_file = open(test_output_path)
    except IOError, e:
      print "current output:"
      print current_output
      raise
    
    test_output = test_file.read()
    if current_output != test_output:
      current_output_path = os.path.join(
        os.path.dirname(filename),
        options.test_output,
        classname + '.failed')
      f = open(current_output_path, 'w')
      f.write(current_output)
      f.close()
      for line in print_lines:
        print >> sys.stderr, ' '.join(line)
      print >> sys.stderr, "FAILED:", classname
      print >> sys.stderr, '  diff -u', test_output_path, current_output_path
      print >> sys.stderr, '  crunner.py -to', filename
      if raised_exception:
        print >> sys.stderr, current_output
      
    else:
      print_output('OK')

  if options.output:
    genfile_name = '%s.py' % classname
    genfile_path = os.path.join(os.path.dirname(filename), genfile_name)
    outfile = open(genfile_path, 'w')
    outfile.write(src_code)
    outfile.close()

if __name__ == '__main__':
  from optparse import OptionParser
  op = OptionParser()
  op.add_option('-t', '--test', action='store_true', default=False)
  op.add_option('--test-input')
  op.add_option('--test-output', default='output',
          help="directory for output")
  op.add_option('--accept-test-result', action='store_true', default=False,
          help='accept current code output as correct for future tests')
  op.add_option('--preserve-optional-whitespace', action='store_false',
          default=True, dest='ignore_optional_whitespace',
          help='preserve leading whitespace before a directive')
  op.add_option('-q', '--quiet', action='store_true', default=False)
  op.add_option('-o', '--output', action='store_true', default=False,
          help='save generated files')
  op.add_option('-O', dest='optimizer_level', type='int', default=0)
  (options, args) = op.parse_args()

  for filename in args:
    process_file(filename, options)
