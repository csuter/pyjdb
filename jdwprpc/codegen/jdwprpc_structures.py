import spec_structures

def jdwprpc_impl(spec):
  return "\n".join([
    "import %s" % ",".join([
        "google.protobuf.message",
        "jdwp",
        "jdwp_pb2",
        "protobuf.socketrpc.server",
        "struct",
        "sys",
        ]),
    server_creator_function(spec.command_sets),
    server_constants(spec.command_sets),
    "\n".join([ command_set_impl(cs) for cs in spec.command_sets ]),
    main_clause() ])

def main_clause():
  return "\n".join([
    "if __name__ == '__main__':",
    "  LaunchServer(int(sys.argv[1]), int(sys.argv[2]))" ])

def server_creator_function(command_sets):
  return "\n".join([
    "def LaunchServer(port, jvm_debug_port):",
    "  print(\"Launching server\")",
    "  # jdwp.Jdwp encapsulates direct wire communication with the jvm",
    "  jdwp = jdwp.Jdwp(int(jvm_debug_port))",
    "  server = protobuf.socketrpc.server.SocketRpcServer(port)",
    "\n".join([
      "  server.registerService(%sImpl(jdwp))" % cs.name for cs in command_sets
      ]),
    "  server.run()",
    "  return server",
    ])

def server_constants(command_sets):
  return "\n".join([
      "COMMAND_SPECS = dict()",
      "def command_specs_key(command_set_id, command_id):",
      "  return \"%s-%s\" % (command_set_id, command_id)",
      "\n".join(["\n".join([
          "COMMAND_SPECS[\"%s-%s\"] = (%s,%s,\"%s\",\"%s\")" % (
              command_set.id, command.id,
              command_set.id, command.id,
              command.request.pack_fmt(),
              command.response.pack_fmt()
              )
          for command in command_set.commands ])
      for command_set in command_sets ]),
      error_messages()
      ])

def command_set_impl(cs):
  return "\n".join([
    "class %sImpl(jdwp_pb2.%s):" % (cs.name, cs.name),
    "  def __init__(self, jdwp):",
    "    self.jdwp = jdwp",
    "\n".join([ "%s" % command_impl(cs, cmd) for cmd in cs.commands ])
    ])

def command_impl(cs, cmd):
  return "\n".join([
    "  def %s_%s(self, controller, request, done):" % (cs.name, cmd.name),
    request_packing_impl(cs, cmd, cmd.request),
    jdwp_call_impl(cs, cmd),
    {
      spec_structures.Response:response_unpacking_impl,
      spec_structures.Event:event_unpacking_impl
      }[type(cmd.response)](cs, cmd, cmd.response),
    "    done.run(response)",
    ])

def request_packing_impl(cs, cmd, request):
  return "\n".join([
      "    data = []",
      "\n".join([
          request_arg_packing_impl("data", cs, cmd, arg, idx)
          for (idx, arg) in enumerate(request.args) ]),
      ])

def jdwp_call_impl(cs, cmd):
  return "\n".join([
      "    reply = self.jdwp.send_command_await_reply(%s, %s, data)" % (
          cs.id, cmd.id),
      ])

def response_unpacking_impl(cs, cmd, response):
  return "\n".join([
      "    response = jdwp_pb2.%s_%s_Response()" % (cs.name, cmd.name),
      "\n".join([
          response_arg_unpacking_impl("reply[%s]" % idx, cs, cmd, arg, idx)
          for (idx, arg) in enumerate(response.args) ]),
      ])

def event_unpacking_impl(cs, cmd, response):
  return "\n".join([
      #"    response = jdwp_pb2.%s_%s_Response()" % (cs.name, cmd.name),
      #"\n".join([
      #    response_arg_unpacking_impl("reply[%s]" % idx, cs, cmd, arg, idx)
      #    for (idx, arg) in enumerate(response.args) ]),
      ])

def request_arg_packing_impl(data, cs, cmd, arg, idx):
  return {
      spec_structures.Simple:simple_request_arg_unpacking_impl,
      spec_structures.Repeat:repeat_request_arg_unpacking_impl,
      }[type(arg)](data, cs, cmd, arg, idx)

def simple_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    data.append(request.%s)" % arg.name

def repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return { spec_structures.Simple:simple_repeat_request_arg_unpacking_impl,
    spec_structures.Group:group_repeat_request_arg_unpacking_impl,
    spec_structures.Select:select_repeat_request_arg_unpacking_impl
    }[type(arg.arg)](data, cs, cmd, arg, idx)

def simple_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "\n".join([
    "    data.append(request.%s)" % arg.name,
    ])

def group_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  group = arg.arg
  return "\n".join([
      "    for item in %s:" % data,
      "      new_item = response.%s.add()" % arg.name,
      "\n".join([
          "      new_item.%s = item[%s]" % (sub_arg.name, idx)
              for (idx, sub_arg) in enumerate(group.args) ])
      ])

def select_repeat_request_arg_unpacking_impl(data, cs, cmd, arg, idx):
  select = arg.arg
  return "\n".join([
      "    select_repeat = []",
      "    for item in request.%s:" % arg.name,
      "      select_repeat.append(jdwp.proto_to_data(item))",
      "    data.append(select_repeat)",
      ])

def response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return {
      spec_structures.Simple:simple_response_arg_unpacking_impl,
      spec_structures.Repeat:repeat_response_arg_unpacking_impl,
      }[type(arg)](data, cs, cmd, arg, idx)

def simple_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    response.%s = %s" % (arg.name, data)

def repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return { spec_structures.Simple:simple_repeat_response_arg_unpacking_impl,
    spec_structures.Group:group_repeat_response_arg_unpacking_impl,
    spec_structures.Select:select_repeat_response_arg_unpacking_impl
    }[type(arg.arg)](data, cs, cmd, arg, idx)

def simple_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "\n".join([
    "    response.%s.extend([ i[0] for i in %s ])" % (arg.name, data),
    ])

def group_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  group = arg.arg
  return "\n".join([
      "    for item in %s:" % data,
      "      new_item = response.%s.add()" % arg.name,
      "\n".join([
          "      new_item.%s = item[%s]" % (sub_arg.name, idx)
              for (idx, sub_arg) in enumerate(group.args) ])
      ])

def select_repeat_response_arg_unpacking_impl(data, cs, cmd, arg, idx):
  return "    response.%s = %s" % (arg.name, data)

def error_messages():
  return '''
ERROR_MESSAGE_LINES = [ line.strip().split("\\t") for line in \
"""0	NONE	No error has occurred.
10	INVALID_THREAD	Passed thread is null, is not a valid thread or has exited.
11	INVALID_THREAD_GROUP	Thread group invalid.
12	INVALID_PRIORITY	Invalid priority.
13	THREAD_NOT_SUSPENDED	If the specified thread has not been suspended by an event.
14	THREAD_SUSPENDED	Thread already suspended.
15	THREAD_NOT_ALIVE	Thread has not been started or is now dead.
20	INVALID_OBJECT	If this reference type has been unloaded and garbage collected.
21	INVALID_CLASS	Invalid class.
22	CLASS_NOT_PREPARED	Class has been loaded but not yet prepared.
23	INVALID_METHODID	Invalid method.
24	INVALID_LOCATION	Invalid location.
25	INVALID_FIELDID	Invalid field.
30	INVALID_FRAMEID	Invalid jframeID.
31	NO_MORE_FRAMES	There are no more Java or JNI frames on the call stack.
32	OPAQUE_FRAME	Information about the frame is not available.
33	NOT_CURRENT_FRAME	Operation can only be performed on current frame.
34	TYPE_MISMATCH	The variable is not an appropriate type for the function used.
35	INVALID_SLOT	Invalid slot.
40	DUPLICATE	Item already set.
41	NOT_FOUND	Desired element not found.
50	INVALID_MONITOR	Invalid monitor.
51	NOT_MONITOR_OWNER	This thread doesn't own the monitor.
52	INTERRUPT	The call has been interrupted before completion.
60	INVALID_CLASS_FORMAT	The virtual machine attempted to read a class file and determined that the file is malformed or otherwise cannot be interpreted as a class file.
61	CIRCULAR_CLASS_DEFINITION	A circularity has been detected while initializing a class.
62	FAILS_VERIFICATION	The verifier detected that a class file, though well formed, contained some sort of internal inconsistency or security problem.
63	ADD_METHOD_NOT_IMPLEMENTED	Adding methods has not been implemented.
64	SCHEMA_CHANGE_NOT_IMPLEMENTED	Schema change has not been implemented.
65	INVALID_TYPESTATE	The state of the thread has been modified, and is now inconsistent.
66	HIERARCHY_CHANGE_NOT_IMPLEMENTED	A direct superclass is different for the new class version, or the set of directly implemented interfaces is different and canUnrestrictedlyRedefineClasses is false.
67	DELETE_METHOD_NOT_IMPLEMENTED	The new class version does not declare a method declared in the old class version and canUnrestrictedlyRedefineClasses is false.
68	UNSUPPORTED_VERSION	A class file has a version number not supported by this VM.
69	NAMES_DONT_MATCH	The class name defined in the new class file is different from the name in the old class object.
70	CLASS_MODIFIERS_CHANGE_NOT_IMPLEMENTED	The new class version has different modifiers and anUnrestrictedlyRedefineClasses and canUnrestrictedlyRedefineClasses is false.
71	METHOD_MODIFIERS_CHANGE_NOT_IMPLEMENTED	A method in the new class version has different modifiers than its counterpart in the old class version and and canUnrestrictedlyRedefineClasses is false.
99	NOT_IMPLEMENTED	The functionality is not implemented in this virtual machine.
100	NULL_POINTER	Invalid pointer.
101	ABSENT_INFORMATION	Desired information is not available.
102	INVALID_EVENT_TYPE	The specified event type id is not recognized.
103	ILLEGAL_ARGUMENT	Illegal argument.
110	OUT_OF_MEMORY	The function needed to allocate memory and no more memory was available for allocation.
111	ACCESS_DENIED	Debugging has not been enabled in this virtual machine. JVMTI cannot be used.
112	VM_DEAD	The virtual machine is not running.
113	INTERNAL	An unexpected internal error has occurred.
115	UNATTACHED_THREAD	The thread being used to call this function is not attached to the virtual machine. Calls must be made from attached threads.
500	INVALID_TAG	object type id or class tag.
502	ALREADY_INVOKING	Previous invoke not complete.
503	INVALID_INDEX	Index is invalid.
504	INVALID_LENGTH	The length is invalid.
506	INVALID_STRING	The string is invalid.
507	INVALID_CLASS_LOADER	The class loader is invalid.
508	INVALID_ARRAY	The array is invalid.
509	TRANSPORT_LOAD	Unable to load the transport.
510	TRANSPORT_INIT	Unable to initialize the transport.
511	NATIVE_METHOD	
512	INVALID_COUNT	The count is invalid.""".split("\\n") ]
ERROR_MESSAGES = dict([ (int(line[0]), line[1:]) for line in ERROR_MESSAGE_LINES ])
'''
