# an 'abstract' base class for a template, seems like a good idea for now

#import StringIO
import cStringIO as StringIO
import repeater

# sentinel class, in case you want to have a default that is None
class __Unspecified(object):
  pass
Unspecified = __Unspecified()


class PlaceholderError(KeyError):
  pass


class SparrowTemplate(object):
  def __init__(self, search_list=None):
    self.search_list = search_list
    self.repeat = repeater.RepeatTracker()
    
  # FIXME: i'm sure this is a little pokey - might be able to speed this up
  # somehow. not sure if it's better to look before leaping or raise.
  # might also want to let users tune whether to prefer keys or attributes
  def resolve_placeholder(self, name, local_vars, default=Unspecified):
    try:
      return local_vars[name]
    except KeyError:
      pass

    try:
      return getattr(self, name)
    except AttributeError:
      pass

    if self.search_list:
      for scope in self.search_list:
        try:
          return scope[name]
        except KeyError:
          pass
        
        try:
          return getattr(scope, name)
        except AttributeError:
          pass

    if default is not Unspecified:
      return default
    else:
      raise PlaceholderError(name,
                             [get_available_placeholders(scope)
                              for scope in self.search_list])

  def get_var(self, name, default=Unspecified, local_vars=None):
    return self.resolve_placeholder(name, local_vars=local_vars,
                                    default=default)

  def has_var(self, name, local_vars):
    if name in local_vars:
      return True

    if hasattr(self, name):
      return True

    if self.search_list:
      for scope in self.search_list:
        if name in scope:
          return True
        if hasattr(scope, name):
          return True
    return False

  @staticmethod
  def new_buffer():
    return StringIO.StringIO()

def get_available_placeholders(scope):
  if isinstance(scope, dict):
    return scope.keys()
  else:
    return dir(scope)
