import new
import os.path
import re
import sys

import sparrow.compiler.codegen
import sparrow.compiler.parser
import sparrow.compiler.scanner
import sparrow.compiler.analyzer
import sparrow.compiler.optimizer

valid_identfier = re.compile('[a-z]\w*', re.IGNORECASE)

def filename2classname(filename):
  classname = os.path.splitext(
    os.path.basename(filename))[0].lower().replace('-', '_')
  if not valid_identfier.match(classname):
    raise SyntaxError(
      'filename "%s" must be valid python identifier' % filename)
  return classname


# @return abstract syntax tree rooted on a TemplateNode
def parse(src_text):
  parser = sparrow.compiler.parser.SparrowParser(
    sparrow.compiler.scanner.SparrowScanner(src_text))
  return sparrow.compiler.parser.wrap_error_reporter(parser, 'goal')


def parse_file(filename):
  f = open(filename, 'r')
  try:
    src_text = f.read().decode('utf8')
    return parse(src_text)
  finally:
    f.close()

# take an AST and generate code from it - this will run the analysis phase
# this doesn't have the same semantics as python's AST operations it would be
# good to have a reason for the inconsistency other than laziness or stupidity
def compile_ast(parse_root,
                classname,
                options=sparrow.compiler.analyzer.default_options):
  ast_root = sparrow.compiler.analyzer.SemanticAnalyzer(
    classname, parse_root, options).get_ast()
  sparrow.compiler.optimizer.OptimizationAnalyzer(
    ast_root, options).optimize_ast()
  code_generator = sparrow.compiler.codegen.CodeGenerator(ast_root, options)
  return code_generator.get_code()

def compile_template(src_text, classname,
                     options=sparrow.compiler.analyzer.default_options):
  
  return compile_ast(parse(src_text), classname, options)

def compile_file(filename, write_file=False,
                 options=sparrow.compiler.analyzer.default_options):
  parse_root = parse_file(filename)
  src_code = compile_ast(parse_root, filename2classname(filename), options)
  if write_file:
    write_src_file(src_code, filename)
    
  return src_code


def write_src_file(src_code, filename):
  classname = filename2classname(filename)
  outfile_name = '%s.py' % classname
  outfile_path = os.path.join(os.path.dirname(filename), outfile_name)
  outfile = open(outfile_path, 'w')
  outfile.write(src_code)
  outfile.close()


# compile a text file into a template object
# this won't recursively import templates, it's just a convenience in the case
# where you need to create a fresh object directly from raw template file
def load_template_file(filename, module_name=None,
                       options=sparrow.compiler.analyzer.default_options):
  class_name = filename2classname(filename)
  if not module_name:
    module_name = class_name

  src_code = compile_file(filename, options=options)
  module = load_module_from_src(src_code, filename, module_name)
  return getattr(module, class_name)

def load_template(template_src, template_name,
                  options=sparrow.compiler.analyzer.default_options):
  class_name = filename2classname(template_name)
  filename = '<%s>' % class_name
  module_name = class_name

  src_code = compile_template(template_src, class_name, options=options)
  module = load_module_from_src(src_code, filename, module_name)
  return getattr(module, class_name)


def load_module_from_src(src_code, filename, module_name):
  module = new.module(module_name)
  sys.modules[module_name] = module

  bytecode = compile(src_code, filename, 'exec')
  exec bytecode in module.__dict__
  return module
