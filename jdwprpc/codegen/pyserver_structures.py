import spec_structures

def py_server_impl(spec):
  return "\n".join([
    "import ".join(["import jdwp_pb2\n", "jdwp_impl\n", "struct\n", "google.protobuf.message\n"]),
    server_constants(spec.command_sets_),
    "\n".join([ command_set_impl(cs) for cs in spec.command_sets_ ])])

def server_constants(command_sets):
  return "\n".join([
      "COMMAND_SPECS = dict()",
      "\n".join(["\n".join([
          "COMMAND_SPECS[\"%s_%s\"] = (%s,%s,\"%s\",\"%s\")" % (
              command_set.name_, command.name_,
              command_set.id_, command.id_,
              command.request_.pack_fmt(),
              command.response_.pack_fmt()
              )
          for command in command_set.commands_ ])
      for command_set in command_sets ])])

def command_set_impl(cs):
  return "\n".join([
    "class %sImpl(jdwp_pb2.%s):" % (cs.name_, cs.name_),
    "  def __init__(self, jdwp):",
    "    self.jdwp_ = jdwp",
    "\n".join([ "%s" % command_impl(cs, cmd) for cmd in cs.commands_ ])
    ])

def command_impl(cs, cmd):
  return "\n".join([
    "  def %s_%s(self, controller, request, done):" % (cs.name_, cmd.name_),
    request_packing_impl(cs, cmd, cmd.request_),
    jdwp_call_impl(cs, cmd),
    {
      spec_structures.Response:response_unpacking_impl,
      spec_structures.Event:event_unpacking_impl
      }[type(cmd.response_)](cs, cmd, cmd.response_),
    "    done.run(response)",
    ])

def request_packing_impl(cs, cmd, request):
  return "\n".join([
      "    data = []",
      "\n".join([
          request_arg_packing_impl("data", cs, cmd, arg, idx)
          for (idx, arg) in enumerate(request.args_) ]),
      ])

def jdwp_call_impl(cs, cmd):
  return "\n".join([
      "    reply = self.jdwp_.call(\"%s_%s\", %s, %s, data)" % (
          cs.name_, cmd.name_, cs.id_, cmd.id_),
      ])

def response_unpacking_impl(cs, cmd, response):
  return "\n".join([
      "    response = jdwp_pb2.%s_%s_Response()" % (cs.name_, cmd.name_),
      "\n".join([
          response_arg_unpacking_impl("reply[%s]" % idx, cs, cmd, arg, idx)
          for (idx, arg) in enumerate(response.args_) ]),
      ])

def event_unpacking_impl(cs, cmd, response):
  return "\n".join([
      #"    response = jdwp_pb2.%s_%s_Response()" % (cs.name_, cmd.name_),
      #"\n".join([
      #    response_arg_unpacking_impl("reply[%s]" % idx, cs, cmd, arg, idx)
      #    for (idx, arg) in enumerate(response.args_) ]),
      ])

def request_arg_packing_impl(data, cs, cmd, arg, idx):
  return {
      spec_structures.Simple:simple_request_arg_unpacking_impl,
      spec_structures.Repeat:repeat_request_arg_unpacking_impl,
      }[type(arg)](data, cs, cmd, arg, idx)

def simple_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    data.append(request.%s)" % arg.name_

def repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return { spec_structures.Simple:simple_repeat_request_arg_unpacking_impl,
    spec_structures.Group:group_repeat_request_arg_unpacking_impl,
    spec_structures.Select:select_repeat_request_arg_unpacking_impl
    }[type(arg.arg_)](data, cs, cmd, arg, idx)

def simple_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "\n".join([
    "    data.append(request.%s)" % arg.name_,
    ])

def group_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  group = arg.arg_
  return "\n".join([
      "    for item in %s:" % data,
      "      new_item = response.%s.add()" % arg.name_,
      "\n".join([
          "      new_item.%s = item[%s]" % (sub_arg.name_, idx)
              for (idx, sub_arg) in enumerate(group.args_) ])
      ])

def select_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  select = arg.arg_
  return "\n".join([
      "    select_repeat = []",
      "    for item in request.%s:" % arg.name_,
      "      select_repeat.append(jdwp_impl.proto_to_data(item))",
      "    data.append(select_repeat)",
      ])

def response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return {
      spec_structures.Simple:simple_response_arg_unpacking_impl,
      spec_structures.Repeat:repeat_response_arg_unpacking_impl,
      }[type(arg)](data, cs, cmd, arg, idx)

def simple_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    response.%s = %s" % (arg.name_, data)

def repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return { spec_structures.Simple:simple_repeat_response_arg_unpacking_impl,
    spec_structures.Group:group_repeat_response_arg_unpacking_impl,
    spec_structures.Select:select_repeat_response_arg_unpacking_impl
    }[type(arg.arg_)](data, cs, cmd, arg, idx)

def simple_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "\n".join([
    "    response.%s.extend([ i[0] for i in %s ])" % (arg.name_, data),
    ])

def group_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  group = arg.arg_
  return "\n".join([
      "    for item in %s:" % data,
      "      new_item = response.%s.add()" % arg.name_,
      "\n".join([
          "      new_item.%s = item[%s]" % (sub_arg.name_, idx)
              for (idx, sub_arg) in enumerate(group.args_) ])
      ])

def select_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    response.%s = %s" % (arg.name_, data)
