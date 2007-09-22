import os.path

import sparrow.compiler.analyzer
import sparrow.compiler.codegen
import sparrow.compiler.parser
import sparrow.compiler.scanner


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
    
def compile_file(filename, write_file=False,
                 options=sparrow.compiler.analyzer.default_options):
  parse_root = parse_file(filename)
  ast_root = sparrow.compiler.analyzer.SemanticAnalyzer(
    filename, parse_root).get_ast()
  code_generator = sparrow.compiler.codegen.CodeGenerator(ast_root)
  src_code = code_generator.get_code()

  if write_file:
    classname = sparrow.compiler.analyzer.filename2classname(filename)
    outfile_name = '%s.py' % classname
    outfile_path = os.path.join(os.path.dirname(filename), outfile_name)
    outfile = open(outfile_path, 'w')
    outfile.write(src_code)
    outfile.close()
  
  return src_code

