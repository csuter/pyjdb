import re

class Spec:
  def __init__(self, spec):
    self.parent_ = None
    self.constant_sets_ = [
        ConstantSet(self, entry) for entry in spec if entry[0] == 'ConstantSet' ]
    self.command_sets_ = [
        CommandSet(self, entry) for entry in spec if entry[0] == 'CommandSet' ]

class ConstantSet:
  def __init__(self, parent, constant_set):
    self.parent_ = parent
    self.name_ = constant_set[1]
    self.constants_ = [ Constant(self, c) for c in constant_set[2:] ]

class CommandSet:
  def __init__(self, parent, command_set):
    self.parent_ = parent
    [self.name_, self.id_] = command_set[1].split("=")
    self.commands_ = [ Command(self, c) for c in command_set[2:] ]

class Constant:
  def __init__(self, parent, constant):
    self.parent_ = parent
    [name, self.value_] = constant[1].split("=")
    self.name_ = "%s_%s" % (parent.name_, name)

class Command:
  def __init__(self, parent, command):
    self.parent_ = parent
    [self.name_, self.id_] = command[1].split("=")
    if command[2][0] == 'Event':
      self.request_ = Request(self, [])
      self.response_ = create_arg_from_spec(self, command[2])
      self.errors_ = []
    else:
      self.request_ = Request(self, command[2])
      self.response_ = Response(self, command[3])
      self.errors_ = [ ErrorRef(self, error) for error in command[4] ]

class Request:
  def __init__(self, parent, request):
    self.parent_ = parent
    self.args_ = [ create_arg_from_spec(parent, arg) for arg in request[1:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args_ ])

class Response:
  def __init__(self, parent, response):
    self.parent_ = parent
    self.args_ = [ create_arg_from_spec(parent, arg) for arg in response[1:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args_ ])

class Simple:
  def __init__(self, parent, simple):
    self.parent_ = parent
    self.type_ = simple[0]
    self.name_ = simple[1]
  def pack_fmt(self):
    return SPECMAP_STRUCT_FMTS[self.type_]

class Repeat:
  def __init__(self, parent, repeat):
    self.parent_ = parent
    self.name_ = repeat[1]
    self.arg_ = create_arg_from_spec(self, repeat[2])
  def pack_fmt(self):
    return "R(%s)" % self.arg_.pack_fmt()

class Group:
  def __init__(self, parent, group):
    self.parent_ = parent
    self.name_ = group[1]
    self.args_ = [ create_arg_from_spec(self, arg) for arg in group[2:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args_ ])

class Select:
  def __init__(self, parent, select):
    self.parent_ = parent
    self.name_ = select[1]
    self.choice_arg_ = create_arg_from_spec(self, select[2])
    self.alts_ = [ Alt(self, alt) for alt in select[3:] ]
  def pack_fmt(self):
    return "?%s(%s)" % (
        self.choice_arg_.pack_fmt(),
        "|".join([ alt.pack_fmt() for alt in self.alts_ ]))

class Alt:
  def __init__(self, parent, alt):
    self.parent_ = parent
    [self.name_, self.position_] = alt[1].split("=")
    if not re.match("[0-9]+", self.position_):
      self.position_ = get_alt_int_position(self)
    self.group_name_ = "%s_%s" % (parent.name_, self.name_)
    self.args_ = [ create_arg_from_spec(parent, arg) for arg in alt[2:] ]
  def pack_fmt(self):
    return "%s=%s" % (
        self.position_,
        "".join([ arg.pack_fmt() for arg in self.args_ ]))

class Event:
  def __init__(self, parent, event):
    self.parent_ = parent
    self.suspend_policy_ = create_arg_from_spec(parent, event[1])
    self.events_= create_arg_from_spec(parent, event[2])
  def pack_fmt(self):
    return "".join([
        self.suspend_policy_.pack_fmt(),
        self.events_.pack_fmt()
        ])

class ErrorRef:
  def __init__(self, parent, error):
    self.parent_ = parent
    self.name_ = error[1]

def create_arg_from_spec(parent, arg):
  arg_type = arg[0]
  try:
    return {
      'Repeat':Repeat,
      'Group':Group,
      'Event':Event,
      'Select':Select}[arg_type](parent, arg)
  except KeyError:
    return Simple(parent, arg)

def get_alt_int_position(alt):
  # a hack ensues. replace with something better.
  spec = alt.parent_
  # find the spec (its parent_ is None)
  while spec.parent_ != None:
    spec = spec.parent_
  # find the "EventKind" constant set. Complain if not exists.
  constants = None
  for constant_set in spec.constant_sets_:
    if constant_set.name_ == "EventKind":
      constants = constant_set.constants_
      break
  if constants == None:
    raise Exception("No EventKind constant set")
  # position looks like "JDWP.EventKind.BREAKPOINT", e.g.
  val = alt.position_.split(".")[2]
  for constant in constants:
    if constant.name_[len("EventKind_"):] == val:
      return constant.value_
  raise Exception("Unrecognized EventType constant: %s" % alt.position_)

SPECMAP_LINES = [ line.strip().split("\t") for line in \
"""string	string	S
boolean	bool	b
byte	int32	B
int	int32	I
long	int64	L
referenceType	int64	L
referenceTypeID	int64	L
threadObject	int64	L
threadGroupObject	int64	L
stringObject	int64	L
object	int64	L
classLoaderObject	int64	L
field	int64	L
method	int64	L
value	Value	V
interfaceType	int64	L
classObject	int64	L
tagged-object	TaggedObjectID	T
classType	int64	L
untagged-value	UntaggedValue	V
arrayType	int64	L
frame	int64	L
location	Location	X
arrayObject	int64	L
typed-sequence	Value	A""".split("\n") ]

SPECMAP_PROTO_TYPES = dict([ (line[0], line[1]) for line in SPECMAP_LINES ])
SPECMAP_STRUCT_FMTS = dict([ (line[0], line[2]) for line in SPECMAP_LINES ])

