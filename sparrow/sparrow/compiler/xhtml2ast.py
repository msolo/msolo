import xml.dom.minidom

from sparrow.compiler.ast import *

import sparrow.compiler.util

class XHTML2AST(object):
  namespace = 'py'
  attr_op_namespace = 'pyattr'
  
  def build_template(self, filename):
    f = open(filename)
    data = f.read().decode('utf8')
    f.close()
    return self.parse(data)

  def parse(self, src_text):
    dom = xml.dom.minidom.parseString(src_text)
    template = TemplateNode()
    template.extend(self.build_ast(dom))
    return template
  
  def build_ast(self, dom_node):
    #print "build_ast", dom_node.nodeName
    node_list = []
    
    if dom_node.attributes:
      # the key types have a precedence that needs to be preserved
      # www.zope.org/Documentation/Books/ZopeBook/2_6Edition/AppendixC.stx
      # since this is also how we scan the tree, on-error is included
      # fixme: content/replace are mutually exclusive, that should generate an
      # error
      op_precedence = [
        'define',
        'condition',
        'repeat',
        'content',
        'content-html',
        'replace',
        'replace-html',
        'attributes',
        'omit-tag',
        'on-error',
        ]

      # some of these operations can alter the output stream (most of them
      # really) - also, some don't exactly make sense to be on the same object
      # as a repeat - for instance, repeat->replace, whereas repeat->attributes
      # makes more sense

      # fixme: do I need keys() here? also, i think that attribute can be None
      attr_name_list = dom_node.attributes.keys()
      processed_any_op = False
      for op in op_precedence:
        op_attr_name = '%s:%s' % (self.namespace, op)
        if op_attr_name in attr_name_list:
          op_handler = 'handle_%s' % op
          # print "op_handler:", op_handler, dom_node.nodeName, dom_node.attributes.keys(), processed_any_op

          node_list.extend(getattr(self, op_handler)(dom_node, op_attr_name))
          processed_any_op = True

      # process attribute namespace
      attr_output_ast = []
      attr_prune_list = []
      # this is horribly un-pythonic - i'm having Java flashbacks
      for i in xrange(dom_node.attributes.length):
        attr = dom_node.attributes.item(i)
        if attr.prefix == self.attr_op_namespace:
          attr_prune_list.append(attr.localName)
          attr_prune_list.append('%s:%s' % (self.attr_op_namespace,
                                            attr.localName))
          attr_output_ast.extend(self.make_attr_node(attr))
          # print "attr_handler:", attr.prefix, attr.localName
          #processed_any_op = True
      for attr_name in attr_prune_list:
        try:
          dom_node.removeAttribute(attr_name)
        except xml.dom.NotFoundErr:
          print "ignoring missing", attr_name

      if not processed_any_op:
        node_list.extend(self.handle_default(dom_node,
                                             attr_ast=attr_output_ast))
    else:
      node_list.extend(self.handle_default(dom_node))

    #for child in dom_node.childNodes:
    #  node_list.extend(self.build_ast(child))

    return node_list

  # attr_ast - allow injecting some ast nodes
  # fixme: feels like it could have a cleaner API
  def handle_default(self, dom_node, attr_ast=None):
    # print "handle_default", dom_node.nodeName, attr_ast
    node_list = []
    if dom_node.nodeType == xml.dom.minidom.Node.ELEMENT_NODE:
      node_list.extend(self.make_tag_node(dom_node, attr_ast=attr_ast))
      for child in dom_node.childNodes:
        node_list.extend(self.build_ast(child))
      node_list.extend(self.make_tag_node(dom_node, close=True))
    elif dom_node.nodeType == xml.dom.minidom.Node.TEXT_NODE:
      node_list.append(TextNode(dom_node.nodeValue))
    elif dom_node.nodeType == xml.dom.minidom.Node.COMMENT_NODE:
      # node_list.append(TextNode(dom_node.nodeValue))
      pass
    elif dom_node.nodeType == xml.dom.minidom.Node.DOCUMENT_NODE:
      for child in dom_node.childNodes:
        node_list.extend(self.build_ast(child))
    elif dom_node.nodeType == xml.dom.minidom.Node.PROCESSING_INSTRUCTION_NODE:
      if dom_node.nodeName == 'py-doctype':
        node_list.append(TextNode(dom_node.nodeValue))
      else:
        raise Exception("unexepected processing instruction: %s" % dom_node)
    else:
      raise Exception("unexepected node type: %s" % dom_node.nodeType)
    return node_list

  def make_tag_node(self, dom_node, close=False, attr_ast=None):
    # print "make_tag_node", dom_node.nodeName, attr_ast
    node_list = []
    node_name = dom_node.nodeName
    if close:
      if dom_node.childNodes:
        node_list.append(TextNode(u'</%(node_name)s>' % vars()))
    else:
      attr_text = ' '.join(['%s="%s"' % (key, value)
                            for key, value in dom_node.attributes.items()
                            if not key.startswith('py:')])
      # fixme: this is starting to look fugly - hard to maintain and error prone
      if dom_node.childNodes:
        if attr_text:
          if attr_ast:
            node_list.append(TextNode(u'<%(node_name)s %(attr_text)s' % vars()))
            node_list.extend(attr_ast)
            node_list.append(TextNode(u'>'))
          else:
            node_list.append(TextNode(u'<%(node_name)s %(attr_text)s>' % vars()))
        else:
          if attr_ast:
            node_list.append(TextNode(u'<%(node_name)s' % vars()))
            node_list.extend(attr_ast)
            node_list.append(TextNode(u'>'))
          else:
            node_list.append(TextNode(u'<%(node_name)s>' % vars()))
      else:
        if attr_text:
          if attr_ast:
            # print "XXX make_tag_node", dom_node.nodeName, attr_ast
            node_list.append(TextNode(u'<%(node_name)s %(attr_text)s' % vars()))
            node_list.extend(attr_ast)
            node_list.append(TextNode(u' />'))
          else:
            node_list.append(TextNode(u'<%(node_name)s %(attr_text)s />' % vars()))
        else:
          if attr_ast:
            node_list.append(TextNode(u'<%(node_name)s' % vars()))
            node_list.extend(attr_ast)
            node_list.append(TextNode(u' />'))
          else:
            node_list.append(TextNode(u'<%(node_name)s />' % vars()))
          
    return node_list

  def make_attr_node(self, attr):
    node_list = []
    new_attr_name = attr.localName
    attr_ast = sparrow.compiler.util.parse(attr.nodeValue, 'rhs_expression')
    node_list.append(TextNode(u' %(new_attr_name)s="' % vars()))
    # fixme: need to guarantee good output - escape sequences etc
    node_list.append(PlaceholderSubstitutionNode(attr_ast))
    node_list.append(TextNode('"'))
    return node_list

  def handle_define(self, dom_node, attr_name):
    node_list = []
    node_name = dom_node.nodeName
    # print "handle_define", node_name
    # fixme: this is a nasty temp hack, it will generate the correct code
    # for 1 define, but multiple expressions won't work
    ast = sparrow.compiler.util.parse(dom_node.getAttribute(attr_name),
                                      'argument_list')
    dom_node.removeAttribute(attr_name)
    node_list.extend(ast)
    node_list.extend(self.build_ast(dom_node))
    return node_list
  
  
  def handle_content(self, dom_node, attr_name):
    node_list = []
    node_name = dom_node.nodeName
    node_list.extend(self.make_tag_node(dom_node))
    expr_ast = sparrow.compiler.util.parse(
      dom_node.getAttribute(attr_name), 'rhs_expression')

#    node_list.append(PlaceholderSubstitutionNode(
#      self.build_udn_path_ast(dom_node.getAttribute(attr_name))))
    node_list.append(PlaceholderSubstitutionNode(expr_ast))
    node_list.extend(self.make_tag_node(dom_node, close=True))
    return node_list

  
  def handle_replace(self, dom_node, attr_name):
    expr_ast = sparrow.compiler.util.parse(
      dom_node.getAttribute(attr_name), 'rhs_expression')
#    return [PlaceholderSubstitutionNode(
#      self.build_udn_path_ast(dom_node.getAttribute(attr_name)))]
    return [PlaceholderSubstitutionNode(expr_ast)]


  def handle_repeat(self, dom_node, attr_name):
    expr_pieces = dom_node.getAttribute(attr_name).split()
    dom_node.removeAttribute(attr_name)
    target = expr_pieces[0]
    expr_ast = sparrow.compiler.util.parse(
      ' '.join(expr_pieces[1:]), 'rhs_expression')
    node_list = []
    # hack - assumes python syntax
    fn = ForNode(
      TargetListNode([IdentifierNode("self.repeat['%s']" % target),
                      IdentifierNode(target)]),
      ExpressionListNode([CallFunctionNode(IdentifierNode('enumerate'),
                                           ArgListNode([expr_ast]))]))
    has_child_stuff = False
    for attr_name in ('py:content', 'py:replace',):
      if dom_node.hasAttribute(attr_name):
        has_child_stuff = True
        break
    else:
      has_child_stuff = bool(dom_node.childNodes)

    if has_child_stuff:
      node_list.append(self.make_tag_node(dom_node))
      for n in dom_node.childNodes:
        fn.extend(self.build_ast(n))
    else:
      fn.extend(self.build_ast(dom_node))
    node_list.append(fn)
    node_list.extend(self.make_tag_node(dom_node, close=True))
    return node_list


  def handle_condition(self, dom_node, attr_name):
    expr_ast = sparrow.compiler.util.parse(
      dom_node.getAttribute(attr_name), 'rhs_expression')
    node_list = []
    if_node = IfNode(expr_ast)
    node_list.append(if_node)
    if_node.append(self.make_tag_node(dom_node))
    for n in dom_node.childNodes:
      if_node.extend(self.build_ast(n))
    if_node.extend(self.make_tag_node(dom_node, close=True))
    return node_list


  def build_udn_path_ast(self, path):
    pieces = path.split('.')
    node = PlaceholderNode(pieces[0])
    for piece in pieces[1:]:
      node = GetUDNNode(node, piece)
    return node
      
if __name__ == '__main__':
  import sys
  import sparrow.compiler.util
  x2a = XHTML2AST()
  filename = sys.argv[1]
  tnode = x2a.build_template(filename)
  print tnode
  classname = sparrow.compiler.util.filename2classname(filename)
  src = sparrow.compiler.util.compile_ast(tnode, classname)
  print src
  module = sparrow.compiler.util.load_module_from_src(src, '<none>', classname)
  tclass = getattr(module, classname)
  d = {
    'test_x': 'x var',
    'test_y': 'y var',
    'test_z': 'z var',
    'test_number_list': [1, 2, 3, 4, 5],
    'test_object_list': [{'id': 1, 'name': 'o1'},
                         {'id': 2, 'name': 'o2'},
                         {'id': 3, 'name': 'o3'},
                         ],
    'test_dict': {'key1': 1},
    'test_whitespaced_dict': {'key 1': 1},
    'test_range': range,
    'content_type': 'test/sparrow',
    }

  print tclass(search_list=[d]).main()
