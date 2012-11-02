# Copyright (c) 2012 Christopher Suter
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
Jdwp package defines 1 class for external use: Jdwp. Its constructor
requires a valid jvm debug port, open on localhost, and an event callback
method. Upon instantiation, the Jdwp object creates a connection to the target
jvm, performs the obligatory handshake, and is then ready to send commands and
receive responses and events. It also instantiates a background reader thread,
which reads and deserializes replies, errors, and events, forwarding these to
the appropriate handler method on Jdwp.

Jdwp's external api mainly consists of the constructor,
send_command_await_reply, and send_command_no_wait. The data structures passed
into and returned from these methods, and the ones passed to the event callback,
are all simply lists of lists matching the structure of the Reply (etc.) section
of the jdwp spec (jdwprpc/codegen/jdwp_spec.txt)

Author: Christopher Suter (cgs1019@gmail.com)
"""

import jdwprpc
import socket
import struct
import threading


class Jdwp:
  '''As described above, provides a simple interface for interacting with a jdwp
  wire connection'''
  def __init__(self, port, event_callback, debug = False):
    '''In addition to setting internal fields, the constructor actually connects
    to the remote jvm and does the handshake. Not sure that's good OOP, but
    it'll have to do for now.'''
    # map from request_id to dicts holding req details
    self.requests_by_request_id = dict()
    # map from request_id to response data
    self.replies_by_request_id = dict()
    # events
    self.events = []
    # we increment this after each req. not thread safe at the moment.
    self.next_request_id = 0
    # we'll call this when events come in from the reader thread
    self.event_callback = event_callback

    self.debug = debug

    self.jdwp_connection = Connection(port)
    self.reader_thread = JdwpReplyPacketReaderThread(self, self.jdwp_connection)
    self.reader_thread.start()

  def send_command_await_reply(self, command_set_id, command_id, data = []):
    '''This really just defers to send_command_no_wait, then calls get_reply
    and handles printing an error message if one was received. Returns [] in
    case of err != 0'''
    # send command and get generated request_id
    request_id = self.send_command_no_wait(command_set_id, command_id, data)
    err, reply_unpacked = self.get_reply(request_id)
    if err != 0:
      self.print_error(request_id, err)
    return err, reply_unpacked

  def send_command_no_wait(self, command_set_id, command_id, data = []):
    request_id = self.next_request_id
    self.next_request_id += 1
    self.requests_by_request_id[request_id] = (command_set_id, command_id, data)
    key = jdwprpc.command_specs_key(command_set_id, command_id)
    fmt = jdwprpc.COMMAND_SPECS[key][2]
    packed_data = pack_jdwp_data(fmt, data, self.debug)
    self.jdwp_connection.send(request_id, command_set_id, command_id, packed_data)
    return request_id

  def get_reply(self, request_id):
    # block until the reply comes
    while request_id not in self.replies_by_request_id:
      None
    return self.replies_by_request_id[request_id]

  def report_event(self, event_unpacked):

    self.events.append(event_unpacked)
    if self.event_callback != None:
      self.event_callback(event_unpacked)

  def report_reply(self, request_id, err, reply_unpacked):
    self.replies_by_request_id[request_id] = (err, reply_unpacked)

  def print_error(self, request_id, err):
    (command_set_id, command_id, request) = \
        self.requests_by_request_id[request_id]
    if self.debug:
      print("JDWP Error! req_id:%d, csid:%d, cid:%d, req:%s, %s=%d: \"%s\"" % (
          request_id,
          command_set_id,
          command_id,
          request,
          jdwprpc.ERROR_MESSAGES[err][0],
          err,
          jdwprpc.ERROR_MESSAGES[err][1]))
  def disconnect(self):
    self.jdwp_connection.disconnect()

class Connection:
  '''Wraps the actual socket connection to remote jvm, and presents two
  methods: send and receive, which take care of converting requests and replies
  to and from jdwp packets.'''
  def __init__(self, port):
    '''Creates socket and connects to remote jvm and performs handshake. Throws
    an Exception if there's a problem.'''
    self.port = port
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.connect(('localhost', self.port))
    # handshake
    self.sock.send(b'JDWP-Handshake')
    data = self.sock.recv(14)
    if data != b'JDWP-Handshake':
      raise Exception('Handshake failed')

  def send(self, request_id, command_set_id, command_id, packed_data):
    '''Writes header and data on wire to jvm'''
    flags = 0
    length = 11 + len(packed_data)
    header = struct.pack(
        ">IIBBB", length, request_id, flags, command_set_id, command_id)
    self.sock.send(header)
    self.sock.send(packed_data)

  def receive(self):
    '''Reads header, flags, error code, and subsequent data from jdwp socket'''
    header = self.sock.recv(11);
    length, request_id, flags, err = struct.unpack('>IIBH', header)
    remaining = length - 11
    msg = bytearray()
    while remaining > 0:
      chunk = self.sock.recv(min(remaining, 4096))
      msg.extend(chunk)
      remaining -= len(chunk)
    data_packed = ''.join([chr(x) for x in msg])
    return request_id, flags, err, data_packed

  def disconnect(self):
    self.sock.close();

class JdwpReplyPacketReaderThread(threading.Thread):
  '''Loops indefinitely, calling Connection.receive, interpretting the response,
  and reporting it via the appropriate method on Jdwp (e.g., report_reply)'''
  def __init__(self, jdwp, jdwp_connection):
    super(JdwpReplyPacketReaderThread, self).__init__(name="jdwp_reader")
    self.jdwp = jdwp
    self.jdwp_connection = jdwp_connection
    self.setDaemon(True)

  def run(self):
    while True:
      try:
        request_id, flags, err, reply_data_packed = self.jdwp_connection.receive()
      except Exception, e:
        print("Error receiving data: %s" % e)
      # events look like replies, but with error code 16484 (16484 is 0x4064
      # which is 0x40 and 0x64, or 64 and 100 - the command_set_id and
      # command_id for Event_Composite)
      if err == 16484:
        (event_unpacked, size) = unpack_jdwp_data(
            jdwprpc.COMMAND_SPECS["64-100"][3], reply_data_packed)
        self.jdwp.report_event(event_unpacked)
      elif err != 0:
        self.jdwp.report_reply(request_id, err, [])
        continue
      else:
        (command_set_id, command_id, request_data) = \
            self.jdwp.requests_by_request_id[request_id]
        key = jdwprpc.command_specs_key(command_set_id, command_id)
        if key not in jdwprpc.COMMAND_SPECS:
          if self.jdwp.debug:
            print("ZOIKS! Unrecognized reply data (%s, %s, %s)" %
                (command_set_id, command_id, reply_data_packed))
          continue
        (reply_unpacked, size) = unpack_jdwp_data(
            jdwprpc.COMMAND_SPECS[key][3], reply_data_packed)
        self.jdwp.report_reply(request_id, err, reply_unpacked)

def unpack_jdwp_data(fmt, packed_data, debug = False):
  '''somehow, magically unpacks wire data structures correctly most of the
  time, using this ill-defined weird little shorthand I (cgs) invented. should
  be rewritten using pyparsing and a well-defined weird little shorthand. this
  is sort of an inverse to pack_jdwp_data.'''
  if debug:
    print("fmt: %s" % fmt)
    print("packed_data: %s" % bytes_to_hex_string(packed_data))
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
      strlen = struct.unpack(">I", packed_data[pos:pos+4])[0]
      result.append(struct.unpack(str(strlen) + "s",
          packed_data[pos+4:pos+strlen+4])[0].decode('UTF-8'))
      size += 4 + strlen
      pos += 4 + strlen
    elif c == 'I':
      result.append(struct.unpack(">I", packed_data[pos:pos+4])[0])
      size += 4
      pos += 4
    elif c == 'b':
      result.append(struct.unpack(">B", packed_data[pos:pos+1])[0] != 0)
      size += 1
      pos += 1
    elif c == 'B':
      result.append(struct.unpack(">B", packed_data[pos:pos+1])[0])
      size += 1
      pos += 1
    elif c == 'L':
      result.append(struct.unpack(">Q", packed_data[pos:pos+8])[0])
      size += 8
      pos += 8
    elif c == 'V':
      tag = struct.unpack(">B", packed_data[0])
      data_size = tag_constants_data_sizes[tag]
      fmt = ">" + "B" * data_size
      value = struct.unpack(fmt, packed_data[1:])
      result.append(tag, value)
      size += 1 + data_size
      pos += 1 + data_size
    elif c == 'T':
      type_tag, object_id = struct.unpack(">BQ", packed_data[pos:pos+9])
      result.append((type_tag, object_id))
      size += 9
      pos += 9
    elif c == 'X':
      type_tag, class_id, method_id, index = struct.unpack(">BQQQ", packed_data[pos:pos+25])
      result.append((type_tag, class_id, method_id, index))
      size += 25
      pos += 25
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION UNPACKING")
    elif c == '?':
      event_kind = struct.unpack(">B", packed_data[pos:pos+1])[0]
      result.append(event_kind)
      sub_data_fmt = get_paren_substr_after(fmt, idx+1)
      clauses = dict((int(k), v)
          for (k, v) in (x.split("=") for x in sub_data_fmt.split("|")))
      (sub_result, sub_result_size) = unpack_jdwp_data(clauses[event_kind], packed_data[pos+1:])
      result.append(sub_result)
      size += 1 + sub_result_size
      idx += 1
      pos += 1
    elif c == 'R':
      num = struct.unpack(">I", packed_data[pos:pos+4])[0]
      pos += 4
      sub_result = []
      if fmt[idx+1] != '(':
        raise Exception("jdi_data fmt exception: expect '(' after 'R'")
      close_paren = find_close_paren(fmt, idx+1)
      if close_paren == -1:
        raise Exception("jdi_data fmt exception: no matching ')'")
      sub_data_fmt = fmt[idx+2:close_paren]
      for i in range(num):
        sub_data, sub_size = unpack_jdwp_data(sub_data_fmt, packed_data[pos:])
        pos += sub_size
        size += sub_size
        sub_result.append(sub_data)
      result.extend(sub_result)
    elif c == '(':
      in_paren = 1
    idx += 1
  return result, size

def pack_jdwp_data(fmt, unpacked_data, debug = False):
  '''somehow, magically packs data structures correctly for wire transport most
  of the time, using this ill-defined weird little shorthand I (cgs) invented.
  should be rewritten using pyparsing and a well-defined weird little
  shorthand. this is sort of an inverse to unpack_jdwp_data.'''
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
      result.extend(struct.pack(">B", unpacked_data[pos]))
      pos += 1
    elif c == 'b':
      # write string length
      result.extend(struct.pack(">B", unpacked_data[pos]))
      pos += 1
    elif c == 'I':
      # write string length
      result.extend(struct.pack(">I", unpacked_data[pos]))
      pos += 1
    elif c == 'L':
      # write string length
      result.extend(struct.pack(">Q", unpacked_data[pos]))
      pos += 1
    elif c == 'S':
      strlen = len(unpacked_data[pos])
      # write string length
      result.extend(struct.pack(">I", strlen))
      result.extend(bytearray(unpacked_data[pos][0],"UTF-8"))
      pos += 1
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION PACKING")
    elif c == '?':
      type_tag, rest = unpacked_data
      type_tag_fmt = fmt[idx+1:idx+2]
      result.extend(pack_jdwp_data(type_tag_fmt, type_tag))
      sub_data_fmt = get_paren_substr_after(fmt, idx+1)
      clauses = dict((int(k), v) for (k, v) in (x.split("=") for x in sub_data_fmt.split("|")))
      result.extend(pack_jdwp_data(clauses[type_tag[0]], rest))
      idx += 1
      pos += 1
    elif c == 'R':
      num = len(unpacked_data[pos])
      result.extend(struct.pack(">I", num))
      sub_result = bytearray()
      sub_data_fmt = get_paren_substr_after(fmt, idx)
      for i in range(num):
        sub_data = pack_jdwp_data(sub_data_fmt, unpacked_data[pos][i])
        sub_result.extend(sub_data)
      pos += 1
      result.extend(sub_result)
    elif c == '(':
      in_paren = 1
    else:
      raise Exception(
          "Unrecognized fmt char %s at %s in \"%s\" unpacked_data: \"%s\"" % \
              (c, idx, fmt, unpacked_data))
    idx += 1
  if debug:
    print("fmt: %s" % fmt)
    print("packed_data: %s" % bytes_to_hex_string(result))
  return result

def proto_to_unpacked_data(proto):
  fields = []
  if hasattr(proto, '_fields'):
    for field in proto._fields:
      value = proto._fields[field]
      if field.label == 3:
        unpacked_data = [ proto_to_data(entry) for entry in value ]
      else:
        unpacked_data = proto_to_unpacked_data(value)
      fields.append((field.number, unpacked_data))
    fields = [ entry[1] for entry in sorted(fields, key = lambda k:k[0]) ]
  else:
    fields = [ proto ]
  return fields

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

def get_paren_substr_after(fmt, idx):
  if fmt[idx+1] != '(':
    raise Exception("jdwp data fmt exception: expected '(' at %d of '%s'" % (idx, fmt))
  close_paren = find_close_paren(fmt, idx+1)
  if close_paren == -1:
    raise Exception("jdwp data fmt exception: no matching ')' for paren at %d of '%s'" % (idx, fmt))
  return fmt[idx+2:close_paren]

def bytes_to_hex_string(some_bytes):
  try:
    return ''.join([ "%02X " % ord(x) for x in some_bytes ]).strip()
  except Exception, e:
    return ''.join([ "%02X " % x for x in some_bytes ]).strip()
