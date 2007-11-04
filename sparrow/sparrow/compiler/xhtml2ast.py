import xml.dom.minidom

from sparrow.compiler.ast import *

import sparrow.compiler.util

class XHTML2AST(object):
  
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
      # fixme: do I need keys() here?
      # the key types have a precedence that needs to be preserved
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
        ]

      attr_name_list = dom_node.attributes.keys()
      processed_attr_op = False
      for op in op_precedence:
        op_attr_name = 'py:%s' % op
        if op_attr_name in attr_name_list:
          op_handler = 'handle_%s' % op
          node_list.extend(getattr(self, op_handler)(dom_node, op_attr_name))
          processed_attr_op = True

      if not processed_attr_op:
        node_list.extend(self.handle_default(dom_node))
    else:
      node_list.extend(self.handle_default(dom_node))

    #for child in dom_node.childNodes:
    #  node_list.extend(self.build_ast(child))

    return node_list

  def handle_default(self, dom_node):
    node_list = []
    if dom_node.nodeType == xml.dom.minidom.Node.ELEMENT_NODE:
      node_list.extend(self.make_tag_node(dom_node))
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

  def make_tag_node(self, dom_node, close=False):
    node_list = []
    node_name = dom_node.nodeName
    if close:
      if dom_node.childNodes:
        node_list.append(TextNode(u'</%(node_name)s>' % vars()))
    else:
      attr_text = ' '.join(['%s="%s"' % (key, value)
                            for key, value in dom_node.attributes.items()
                            if not key.startswith('py:')])
      if dom_node.childNodes:
        if attr_text:
          node_list.append(TextNode(u'<%(node_name)s %(attr_text)s>' % vars()))
        else:
          node_list.append(TextNode(u'<%(node_name)s>' % vars()))
      else:
        if attr_text:
          node_list.append(TextNode(u'<%(node_name)s %(attr_text)s />' % vars()))
        else:
          node_list.append(TextNode(u'<%(node_name)s />' % vars()))
          
    return node_list

  def handle_define(self, dom_node, attr_name):
    node_list = []
    node_name = dom_node.nodeName
    #print "handle_define", ast
    # fixme: this is a nasty temp hack, it will generate the correct code
    # for 1 define, but multiple expressions won't work
    ast = sparrow.compiler.util.parse(dom_node.getAttribute(attr_name),
                                      'argument_list')
    node_list.extend(ast)
    node_list.extend(self.make_tag_node(dom_node))
    return node_list
  
  
  def handle_content(self, dom_node, attr_name):
    node_list = []
    node_name = dom_node.nodeName
    node_list.extend(self.make_tag_node(dom_node))
    node_list.append(PlaceholderSubstitutionNode(
      self.build_udn_path_ast(dom_node.getAttribute(attr_name))))
    node_list.extend(self.make_tag_node(dom_node, close=True))
    return node_list

  
  def handle_replace(self, dom_node, attr_name):
    return [PlaceholderSubstitutionNode(
      self.build_udn_path_ast(dom_node.getAttribute(attr_name)))]

  def handle_repeat(self, dom_node, attr_name):
    target, expression = dom_node.getAttribute(attr_name).split()
    node_list = []
    #AssignNode('=', IdentifierNode('repeat'), IdentifierNode('{}'))]
    fn = ForNode(
      TargetListNode([IdentifierNode("self.repeat['%s']" % target),
                      IdentifierNode(target)]),
      ExpressionListNode([CallFunctionNode(IdentifierNode('enumerate'),
                                           ArgListNode([self.build_udn_path_ast(expression)]))]))
    
    node_list.append(self.make_tag_node(dom_node))
    for n in dom_node.childNodes:
      fn.extend(self.build_ast(n))
    node_list.append(fn)
    node_list.extend(self.make_tag_node(dom_node, close=True))
    return node_list


  def handle_condition(self, dom_node, attr_name):
    expression = dom_node.getAttribute(attr_name)
    node_list = []
    if_node = IfNode(self.build_udn_path_ast(expression))
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
    }

  print tclass(search_list=[d]).main()
