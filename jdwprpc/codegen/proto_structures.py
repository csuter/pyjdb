import re
import spec_structures

def spec_proto_def(spec):
  return "\n".join([
      "\n".join([ constant_set_proto_def(c) for c in spec.constant_sets ]),
      "\n".join([ command_set_proto_def(c) for c in spec.command_sets ])
      ])

def constant_set_proto_def(constant_set):
  return "\n".join([
      "enum %s {" % constant_set.name,
      "\n".join([ constant_proto_def(c) for c in constant_set.constants ]),
      "}"
      ])

def constant_proto_def(constant):
  return "%s = %s;" % (
      constant.name,
      to_pb_int(constant.value))

def command_set_proto_def(command_set):
  return "\n".join([
      "\n".join([ command_proto_def(c) for c in command_set.commands ]),
      "service %s {" % command_set.name,
      "\n".join([ rpc_for_name(c.parent.name, c.name) for c in command_set.commands ]),
      "}"])

def command_proto_def(command):
  return "\n".join([
      request_proto_def(command.request),
      { spec_structures.Response:response_proto_def,
          spec_structures.Event:event_proto_def
          }[type(command.response)](command.response)])

def request_proto_def(request):
  return "\n".join([
      "message %s_%s_Request {" % (request.parent.parent.name, request.parent.name),
      "\n".join([ arg_proto_def(arg, idx+1) for (idx, arg) in enumerate(request.args) ]),
      "}"])

def response_proto_def(response):
  return "\n".join([
      "message %s_%s_Response {" % (response.parent.parent.name, response.parent.name),
      "\n".join([ arg_proto_def(arg, idx+1) for (idx, arg) in enumerate(response.args) ]),
      "}"])

def event_proto_def(event):
  return "\n".join([
      "message Event_Composite_Response {",
      arg_proto_def(event.suspend_policy, idx = 1),
      arg_proto_def(event.events, idx = 2),
      "}"])

def arg_proto_def(arg, idx):
  return { spec_structures.Simple:simple_arg_proto_def,
      spec_structures.Repeat:repeat_arg_proto_def,
      spec_structures.Group:group_arg_proto_def,
      spec_structures.Event:event_arg_proto_def}[type(arg)](arg, idx)

def simple_arg_proto_def(arg, idx, modifier = "required"):
  if modifier == "repeated":
    return pb_field( modifier, spec_structures.SPECMAP_PROTO_TYPES[arg.type], arg.parent.name, idx)

  return pb_field( modifier, spec_structures.SPECMAP_PROTO_TYPES[arg.type], arg.name, idx)

def repeat_arg_proto_def(repeat, idx):
  return {
      spec_structures.Simple:simple_arg_proto_def,
      spec_structures.Group:group_arg_proto_def,
      spec_structures.Select:select_arg_proto_def
      }[type(repeat.arg)](repeat.arg, idx, "repeated")

def group_arg_proto_def(group, idx, modifier = "repeated"):
  return "\n".join([
      "message %s {" % group.name,
      "\n".join([ arg_proto_def(arg, idx+1) for (idx, arg) in enumerate(group.args) ]),
      "}",
      pb_field(modifier, group.name, group.parent.name, idx)])

def event_arg_proto_def(arg, idx):
  return "EVENT"

def select_arg_proto_def(select, idx, modifier = "repeated"):
  return "\n".join([
      "message %s {" % select.name,
      simple_arg_proto_def(select.choice_arg, idx = 1),
      "\n".join([ alt_arg_proto_def(alt, idx + 2) for (idx, alt) in enumerate(select.alts) ]),
      "}",
      pb_field(modifier, select.name, select.parent.name, idx),
      ])

def alt_arg_proto_def(alt, idx):
  return "\n".join([
      "message %s {" % alt.group_name,
      "\n".join([ arg_proto_def(arg, idx+1) for (idx, arg) in enumerate(alt.args) ]),
      "}",
      pb_field("optional", alt.group_name, alt.name, idx)])

def to_pb_int(spec_constant):
  if re.match("[0-9]+", spec_constant):
    # it's an int literal
    return  spec_constant
  elif re.match("0x[0-9]+", spec_constant):
    # it's a hex int
    return int.fromhex(spec_constant)
  # it's a char in single quotes like 'x'
  return ord(spec_constant[1])

def rpc_for_name(service_name, name):
  return "rpc %s_%s (%s_%s_Request) returns (%s_%s_Response);\n" % (
      service_name, name, service_name, name, service_name, name)

def pb_field(modifier, field_type, name, number):
    return "%s %s %s = %s;" % (
        modifier, field_type, name, number)
