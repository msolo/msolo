import copy
import os.path

from sparrow.compiler.ast import *

def tree_walker(node):
  yield node
  for n in node.child_nodes:
    for ng in tree_walker(n):
      yield ng
  
class SemanticAnalyzerError(Exception):
  pass

class AnalyzerOptions(object):

  def __init__(self, **kargs):
    self.collapse_adjacent_text = False
    self.collapse_optional_whitespace = False
    self.__dict__.update(kargs)
  def update(self, **kargs):
    self.__dict__.update(kargs)
  
default_options = AnalyzerOptions()
o1_options = copy.copy(default_options)
o1_options.collapse_adjacent_text = True

optimizer_map = {
  0: default_options,
  1: o1_options,
  }

# convert the parse tree into something a bit more 'fat' and useful
# is this an AST? i'm not sure. it will be a tree of some sort
# this should simplify the codegen stage into a naive traversal
# even though this uses memory, i'll make a copy instead of decorating the
# original tree so i can compare the differences
class SemanticAnalyzer(object):
  def __init__(self, classname, parse_root, options=default_options):
    self.classname = classname
    self.parse_root = parse_root
    self.options = options
    self.ast_root = None
    self.template = None

  def get_ast(self):
    ast_node_list = self.build_ast(self.parse_root)
    if len(ast_node_list) != 1:
      raise SemanticAnalyzerError('ast must have 1 root node')
    self.ast_root = ast_node_list[0]
    return self.ast_root

  # build an AST node list from a single parse node
  # need the parent in case we are going to delete a node
  def build_ast(self, node):
    method_name = 'analyze%s' % node.__class__.__name__
    method = getattr(self, method_name, self.default_analyze_node)
    ast_node_list = method(node)
    try:
      if len(ast_node_list) != 1:
        return ast_node_list
    except TypeError, e:
      raise SemanticAnalyzerError('method: %s, result: %s' % (
        method, ast_node_list))
    ast_node = ast_node_list[0]
    return ast_node_list

  def default_analyze_node(self, pnode):
    return [pnode.copy()]
  
  def analyzeTemplateNode(self, pnode):
    self.template = pnode.copy(copy_children=False)
    self.template.classname = self.classname
    for pn in pnode.child_nodes:
      self.template.main_function.extend(self.build_ast(pn))
    self.optimize_child_nodes(self.template.main_function.child_nodes)
    return [self.template]

  def analyzeForNode(self, pnode):
    for_node = ForNode()

    for pn in pnode.target_list.child_nodes:
      for_node.target_list.extend(self.build_ast(pn))
    for pn in pnode.expression_list.child_nodes:
      for_node.expression_list.extend(self.build_ast(pn))
    for pn in pnode.child_nodes:
      for_node.extend(self.build_ast(pn))
    self.optimize_child_nodes(for_node.child_nodes)
    return [for_node]

  def analyzeGetUDNNode(self, pnode):
    get_udn_node = GetUDNNode(self.build_ast(pnode.expression)[0], pnode.name)
    return [get_udn_node]

  def analyzeIfNode(self, pnode):
    if_node = IfNode()
    if_node.test_expression = self.build_ast(pnode.test_expression)[0]
    for pn in pnode.child_nodes:
      if_node.extend(self.build_ast(pn))
    for pn in pnode.else_:
      if_node.else_.extend(self.build_ast(pn))
    self.optimize_child_nodes(if_node.child_nodes)
    self.optimize_child_nodes(if_node.else_)
    return [if_node]


  def analyzeSliceNode(self, pnode):
    snode = pnode
    snode.expression = self.build_ast(pnode.expression)[0]
    snode.slice_expression = self.build_ast(pnode.slice_expression)[0]
    return [snode]

  # FIXME: should I move this to a directive?
  def analyzeImplementsNode(self, pnode):
    if pnode.name == 'library':
      self.template.library = True
    else:
      self.template.main_function.name = pnode.name
      
    return []

  def analyzeImportNode(self, pnode):
    node = ImportNode([self.build_ast(n)[0] for n in pnode.module_name_list])
    self.template.import_nodes.append(node)
    return []

  def analyzeExtendsNode(self, pnode):
    self.analyzeImportNode(pnode)

    # actually want to reference the class within the module name
    pnode = copy.deepcopy(pnode)
    pnode.module_name_list.append(pnode.module_name_list[-1])
    self.template.extends_nodes.append(pnode)
    return []

  def analyzeFromNode(self, pnode):
    self.template.from_nodes.append(pnode.copy())
    return []

  def analyzeTextNode(self, pnode):
    if pnode.child_nodes:
      raise SemanticAnalyzerError("TextNode can't have children")
    return [pnode.copy()]

  def analyzeDefNode(self, pnode):
    #if not pnode.child_nodes:
    #  raise SemanticAnalyzerError("DefNode must have children")
    function = FunctionNode(pnode.name)
    if pnode.parameter_list:
      function.parameter_list = self.build_ast(pnode.parameter_list)[0]

    function.parameter_list.child_nodes.insert(0,
                           ParameterNode(name='self'))
    for pn in pnode.child_nodes:
      function.extend(self.build_ast(pn))
      
    self.optimize_child_nodes(function.child_nodes)
    
    self.template.append(function)
    return []

  def analyzeAttributeNode(self, pnode):
    self.template.attr_nodes.append(pnode.copy())
    return []

  def analyzeBlockNode(self, pnode):
    #if not pnode.child_nodes:
    #  raise SemanticAnalyzerError("BlockNode must have children")
    self.analyzeDefNode(pnode)
    function_node = CallFunctionNode()
    function_node.expression = PlaceholderNode(pnode.name)
    return [PlaceholderSubstitutionNode(function_node)]

  def analyzePlaceholderSubstitutionNode(self, pnode):
    return [PlaceholderSubstitutionNode(
      self.build_ast(pnode.expression)[0])]

  def analyzeCommentNode(self, pnode):
    return []

  def analyzeCallFunctionNode(self, pnode):
    fn = pnode.copy()
    # fixme: the problem here is that this means that some fallout
    # from python code generation is percolating into the semantic
    # analysis phase. i think that's wrong - but i'm not 100% sure
    if (isinstance(fn.expression, PlaceholderNode) and
        fn.expression.name in ('get_var', 'has_var')):
      # fixme: total cheat here
      fn.expression = IdentifierNode('self.%s' % fn.expression.name)
      local_vars = ParameterNode(
        'local_vars',
        CallFunctionNode(IdentifierNode('locals')))
      fn.arg_list.append(local_vars)
    return [fn]

  def optimize_child_nodes(self, node_list):
    optimized_nodes = []
    for n in node_list:
      # collapse optional whitespace by stripping out the nodes
      if (self.options.collapse_optional_whitespace and
          isinstance(n, OptionalWhitespaceNode)):
        continue
      # collapse adjacent TextNodes so we are calling these buffer writes
      elif (self.options.collapse_adjacent_text and
            isinstance(n, TextNode) and
            len(optimized_nodes) and
            isinstance(optimized_nodes[-1], TextNode)):
        optimized_nodes[-1].append_text_node(n)
      else:
        optimized_nodes.append(n)
    #print "optimized_nodes", node_list, optimized_nodes
    node_list[:] = optimized_nodes

      
