import re

class Spec:
  def __init__(self, spec):
    self.parent = None
    self.constant_sets = [
        ConstantSet(self, entry) for entry in spec if entry[0] == 'ConstantSet' ]
    self.command_sets = [
        CommandSet(self, entry) for entry in spec if entry[0] == 'CommandSet' ]

class ConstantSet:
  def __init__(self, parent, constant_set):
    self.parent = parent
    self.name = constant_set[1]
    self.constants = [ Constant(self, c) for c in constant_set[2:] ]

class CommandSet:
  def __init__(self, parent, command_set):
    self.parent = parent
    [self.name, self.id] = command_set[1].split("=")
    self.commands = [ Command(self, c) for c in command_set[2:] ]

class Constant:
  def __init__(self, parent, constant):
    self.parent = parent
    [name, self.value] = constant[1].split("=")
    self.name = "%s_%s" % (parent.name, name)

class Command:
  def __init__(self, parent, command):
    self.parent = parent
    [self.name, self.id] = command[1].split("=")
    if command[2][0] == 'Event':
      self.request = Request(self, [])
      self.response = create_arg_from_spec(self, command[2])
      self.errors = []
    else:
      self.request = Request(self, command[2])
      self.response = Response(self, command[3])
      self.errors = [ ErrorRef(self, error) for error in command[4] ]

class Request:
  def __init__(self, parent, request):
    self.parent = parent
    self.args = [ create_arg_from_spec(parent, arg) for arg in request[1:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args ])

class Response:
  def __init__(self, parent, response):
    self.parent = parent
    self.args = [ create_arg_from_spec(parent, arg) for arg in response[1:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args ])

class Simple:
  def __init__(self, parent, simple):
    self.parent = parent
    self.type = simple[0]
    self.name = simple[1]
  def pack_fmt(self):
    return SPECMAP_STRUCT_FMTS[self.type]

class Repeat:
  def __init__(self, parent, repeat):
    self.parent = parent
    self.name = repeat[1]
    self.arg = create_arg_from_spec(self, repeat[2])
  def pack_fmt(self):
    return "R(%s)" % self.arg.pack_fmt()

class Group:
  def __init__(self, parent, group):
    self.parent = parent
    self.name = group[1]
    self.args = [ create_arg_from_spec(self, arg) for arg in group[2:] ]
  def pack_fmt(self):
    return "".join([ arg.pack_fmt() for arg in self.args ])

class Select:
  def __init__(self, parent, select):
    self.parent = parent
    self.name = select[1]
    self.choice_arg = create_arg_from_spec(self, select[2])
    self.alts = [ Alt(self, alt) for alt in select[3:] ]
  def pack_fmt(self):
    return "?%s(%s)" % (
        self.choice_arg.pack_fmt(),
        "|".join([ alt.pack_fmt() for alt in self.alts ]))

class Alt:
  def __init__(self, parent, alt):
    self.parent = parent
    [self.name, self.position] = alt[1].split("=")
    if not re.match("[0-9]+", self.position):
      self.position = get_alt_int_position(self)
    self.group_name = "%s_%s" % (parent.name, self.name)
    self.args = [ create_arg_from_spec(parent, arg) for arg in alt[2:] ]
  def pack_fmt(self):
    return "%s=%s" % (
        self.position,
        "".join([ arg.pack_fmt() for arg in self.args ]))

class Event:
  def __init__(self, parent, event):
    self.parent = parent
    self.suspend_policy = create_arg_from_spec(parent, event[1])
    self.events= create_arg_from_spec(parent, event[2])
  def pack_fmt(self):
    return "".join([
        self.suspend_policy.pack_fmt(),
        self.events.pack_fmt()
        ])

class ErrorRef:
  def __init__(self, parent, error):
    self.parent = parent
    self.name = error[1]

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
  spec = alt.parent
  # find the spec (its parent_ is None)
  while spec.parent != None:
    spec = spec.parent
  # find the "EventKind" constant set. Complain if not exists.
  constants = None
  for constant_set in spec.constant_sets:
    if constant_set.name == "EventKind":
      constants = constant_set.constants
      break
  if constants == None:
    raise Exception("No EventKind constant set")
  # position looks like "JDWP.EventKind.BREAKPOINT", e.g.
  val = alt.position.split(".")[2]
  for constant in constants:
    if constant.name[len("EventKind_"):] == val:
      return constant.value
  raise Exception("Unrecognized EventType constant: %s" % alt.position)

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
