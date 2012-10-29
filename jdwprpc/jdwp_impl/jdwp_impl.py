import google.protobuf.descriptor
import jdwprpc
import socket
import struct
import threading
import time

class Jdwp:
  def __init__(self, port = 5005):
    # Open jdwp connection and do handshake
    self._establish_connection(port)
    # Initialize event listener thread
    self._init_event_listener()

    # dict of req_id -> (cmd_set, cmd)
    self.requests = dict()
    # dict of req_id -> reply
    self.replies = dict()
    # request ids are simply created sequentially starting with 0
    self.next_req_id = 0

  def _establish_connection(self, port):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.connect(('localhost', port))
    # handshake
    self.sock.send(b'JDWP-Handshake')
    data = self.sock.recv(14)
    if data != b'JDWP-Handshake':
      raise Exception('Failed handshake')

  def _init_event_listener(self):
    self.reader_thread = EventListenerThread()
    self.reader_thread.jdwp = self
    self.reader_thread.start()

  def event(data):
    print("Got an event: %s" % data)
    print("That's all we know.")

  def call(self, name, cmd_set, cmd, data):
    return self.pop_reply(self.call_async(name, cmd_set, cmd, data))

  def call_async(self, name, cmd_set, cmd, data):
    req_id = self.next_id()
    self.requests[req_id] = name
    packed_data = pack_jdi_data(jdwprpc.COMMAND_SPECS[name][2], data)
    self.data_send(req_id, cmd_set, cmd, packed_data)
    return req_id

  def get_reply(self, req_id):
    if req_id not in self.replies:
      while req_id not in self.replies:
        1
    if self.requests[req_id] in jdwprpc.COMMAND_SPECS:
      key = self.requests[req_id]
      _, err, data = self.replies[req_id]
      if err != 0:
        raise Exception("JDWP Error(%s=%d): \"%s\"" % (
            ERROR_MESSAGES[err][0], err, ERROR_MESSAGES[err][1]))
      return unpack_jdi_data(jdwprpc.COMMAND_SPECS[key][3], data)[0]
    return []

  def pop_reply(self, req_id):
    result = self.get_reply(req_id)
    del self.replies[req_id]
    del self.requests[req_id]
    return result

  def data_send(self, req_id, cmdset, cmd, data):
    flags = 0
    length = 11 + len(data)
    header = struct.pack(">IIBBB", length, req_id, flags, cmdset, cmd)
    print("SEND: %s" % data)
    self.sock.send(header)
    self.sock.send(data)

  def data_recv(self):
    header = read_all(self.sock, 11)
    length, req_id, flags, err = struct.unpack('>IIBH', header)
    remaining = length - 11
    data = read_all(self.sock, remaining)
    print("READ: %s" % data)
    return req_id, flags, err, data

  def next_id(self):
    self.next_req_id += 1
    return self.next_req_id

def read_all(sock, num_bytes):
  msgparts = []
  remaining = num_bytes
  while remaining > 0:
    chunk = sock.recv(remaining)
    msgparts.append(chunk)
    remaining -= len(chunk)
  return b''.join(msgparts)


def unpack_jdi_data(fmt, data):
  result = []
  pos = 0
  in_paren = 0
  size = 0
  idx = 0
  while idx < len(fmt):
    c = fmt[idx]
    if in_paren > 0:
      if c == '(':
        in_paren += 1
      elif c == ')':
        in_paren -= 1
      idx += 1
      continue
    if c == 'S':
      strlen = struct.unpack(">I", data[pos:pos+4])[0]
      result.append(struct.unpack(str(strlen) + "s",
          data[pos+4:pos+strlen+4])[0].decode('UTF-8'))
      size += 4 + strlen
      pos += 4 + strlen
    elif c == 'I':
      result.append(struct.unpack(">I", data[pos:pos+4])[0])
      size += 4
      pos += 4
    elif c == 'b':
      result.append(struct.unpack(">B", data[pos:pos+1])[0] != 0)
      size += 1
      pos += 1
    elif c == 'B':
      result.append(struct.unpack(">B", data[pos:pos+1])[0])
      size += 1
      pos += 1
    elif c == 'L':
      result.append(struct.unpack(">Q", data[pos:pos+8])[0])
      size += 8
      pos += 8
    elif c == 'V':
      value, value_size = parse_jdi_value(data)
      result.append(value)
      size += value_size
      pos += value_size
    elif c == 'T':
      type_tag, object_id = struct.unpack(">BQ", data[pos:pos+9])
      result.append((type_tag, object_id))
      size += 9
      pos += 9
    elif c == 'X':
      type_tag, class_id, method_id, index = struct.unpack(">BQQQ", data[pos:pos+25])
      result.append((type_tag, class_id, method_id, index))
      size += 25
      pos += 25
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION UNPACKING")
    #elif c == '?':
    elif c == 'R':
      num = struct.unpack(">I", data[pos:pos+4])[0]
      pos += 4
      sub_result = []
      if fmt[idx+1] != '(':
        raise Exception("jdi_data fmt exception: expect '(' after 'R'")
      close_paren = find_close_paren(fmt, idx+1)
      if close_paren == -1:
        raise Exception("jdi_data fmt exception: no matching ')'")
      sub_data_fmt = fmt[idx+2:close_paren]
      for i in range(num):
        sub_data, sub_size = unpack_jdi_data(sub_data_fmt, data[pos:])
        pos += sub_size
        size += sub_size
        sub_result.append(sub_data)
      result.append(sub_result)
    elif c == '(':
      in_paren = 1
    idx += 1
  return result, size


def parse_jdi_value(data):
  tag = struct.unpack(">B", data[0])
  data_size = tag_constants_data_sizes[tag]
  fmt = ">" + "B" * data_size
  data = struct.unpack(fmt, data[1:])
  return (tag, data), 1 + data_size


def find_close_paren(string, start):
  count = 1
  if string[start] == '(':
    idx = start + 1
  else:
    idx = start
  while count > 0:
    if string[idx] == '(':
      count += 1
    elif string[idx] == ')':
      count -= 1
    idx += 1
  return idx-1


def pack_jdi_data(fmt, data):
  result = bytearray()
  pos = 0
  in_paren = 0
  idx = 0
  while idx < len(fmt):
    c = fmt[idx]
    if in_paren > 0:
      if c == '(':
        in_paren += 1
      elif c == ')':
        in_paren -= 1
      idx += 1
      continue
    elif c == 'B':
      # write string length
      result.extend(struct.pack(">B", data[pos]))
      pos += 1
    elif c == 'b':
      # write string length
      result.extend(struct.pack(">B", data[pos]))
      pos += 1
    elif c == 'I':
      # write string length
      result.extend(struct.pack(">I", data[pos]))
      pos += 1
    elif c == 'L':
      # write string length
      result.extend(struct.pack(">Q", data[pos]))
      pos += 1
    elif c == 'S':
      strlen = len(data[pos])
      # write string length
      result.extend(struct.pack(">I", strlen))
      result.extend(bytearray(data[pos][0],"UTF-8"))
      pos += 1
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION PACKING")
    elif c == '?':
      type_tag, rest = data
      type_tag_fmt = fmt[idx+1:idx+2]
      result.extend(pack_jdi_data(type_tag_fmt, type_tag))
      sub_data_fmt = get_paren_substr_after(fmt, idx+1)
      clauses = dict((int(k), v) for (k, v) in (x.split("=") for x in sub_data_fmt.split("|")))
      result.extend(pack_jdi_data(clauses[type_tag[0]], rest))
      idx += 1
      pos += 1
    elif c == 'R':
      num = len(data[pos])
      result.extend(struct.pack(">I", num))
      sub_result = bytearray()
      sub_data_fmt = get_paren_substr_after(fmt, idx)
      for i in range(num):
        sub_data = pack_jdi_data(sub_data_fmt, data[pos][i])
        sub_result.extend(sub_data)
      pos += 1
      result.extend(sub_result)
    elif c == '(':
      in_paren = 1
    else:
      raise Exception("Unrecognized fmt char %s at idx %s in fmt \"%s\" for data \"%s\"" % (
          c, idx, fmt, data))
    idx += 1
  return result

def proto_to_data(proto):
  fields = []
  if hasattr(proto, '_fields'):
    for field in proto._fields:
      value = proto._fields[field]
      if field.label == 3:
        data = [ proto_to_data(entry) for entry in value ]
      else:
        data = proto_to_data(value)
      fields.append((field.number, data))
    fields = [ entry[1] for entry in sorted(fields, key = lambda k:k[0]) ]
  else:
    fields = [ proto ]
  return fields

def get_paren_substr_after(fmt, idx):
  if fmt[idx+1] != '(':
    raise Exception("jdi_data fmt exception: expected '(' at %d of '%s'" % (idx, fmt))
  close_paren = find_close_paren(fmt, idx+1)
  if close_paren == -1:
    raise Exception("jdi_data fmt exception: no matching ')' for paren at %d of '%s'" % (idx, fmt))
  return fmt[idx+2:close_paren]

class EventListenerThread(threading.Thread):
  def run(self):
    while True:
      reply_id, flags, err, data = self.jdwp.data_recv()
      # events look like replies with error code 16484
      if err == 16484:
        self.jdwp.event(data)
      else:
        self.jdwp.replies[reply_id] = (flags, err, data)

ERROR_MESSAGE_LINES = [ line.strip().split("\t") for line in \
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
512	INVALID_COUNT	The count is invalid.""".split("\n") ]
ERROR_MESSAGES = dict([ (int(line[0]), line[1:]) for line in ERROR_MESSAGE_LINES ])
