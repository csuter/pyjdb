import codegen.spec_structures
import datautils
import pyparsing as pp
import re
import socket
import struct
import threading
import time
import types

class Jdwp:
  def __init__(self, jvm_port, raw_jdwp_spec_text, event_callback=None):
    self.reqs_by_req_id = dict()
    self.replies_by_req_id = dict()
    self.events = []
    self.next_req_id = 1
    self.event_callback = event_callback

    # cleanup spec and parse
    clean_spec_text = re.sub("\s*=\s*", "=", raw_jdwp_spec_text)
    self.parsed_jdwp_spec = \
        self.spec_file_grammar(with_strings=False).parseString(clean_spec_text)
    self.spec = codegen.spec_structures.Spec(self.parsed_jdwp_spec)

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.connect(('localhost', jvm_port))
    # handshake
    handshake = b'JDWP-Handshake'
    self.sock.send(handshake)
    data = self.sock.recv(len(handshake))
    if data != handshake:
      self.sock.close()
      raise Exception('Handshake failed')

    self.reader_thread = ReaderThread(self)

    self.cs_ids_by_name = dict([ (cs.name, cs.id) for cs in self.spec.command_sets ])
    self.command_dicts_by_command_set_name = dict([
        (cs.name, dict([(cmd.name, cmd) for cmd in cs.commands]))
            for cs in self.spec.command_sets])
    self.service_types = {}
    self.__id_sizes = []
    self.__id_sizes = self.VirtualMachine.IDSizes()

  def __getattr__(self, service):
    if service not in self.cs_ids_by_name:
      raise Exception("service %s unknown" % service)

    class abstract_service(object):
      def __init__(subself):
        subself.methods = {}
      def __getattr__(subself, method):
        if method not in self.command_dicts_by_command_set_name[service]:
          raise Exception("No method %s in service %s" % (method, service))
        if method not in subself.methods:
          subself.methods[method] = self.get_method(service, method)
        return subself.methods[method]

    if service not in self.service_types:
      self.service_types[service] = \
          type(service, (abstract_service,), {})()
    return self.service_types[service]

  def get_method(self, service, method):
    return lambda *args : self.__command_request(service, method, args)

  def __command_request(self, service, method, args):
    cs_id = int(self.cs_ids_by_name[service])
    commands = self.command_dicts_by_command_set_name[service]
    command = commands[method]
    cmd_id = int(command.id)
    req_fmt = command.request.pack_fmt()
    resp_fmt = command.response.pack_fmt()
    req_bytes = datautils.to_bytestring(req_fmt, args, self.__id_sizes)
    resp_bytes = self.send_command_sync(cs_id, cmd_id, req_bytes)
    resp_data = datautils.from_bytearray(resp_fmt, resp_bytes, self.__id_sizes)
    response_fields = self.__parse_response(command, resp_data)
    return response_fields

  def __parse_response(self, command, resp_data):
    return self.__parse_response_for_args(command.response.args, resp_data)

  def __parse_response_for_args(self, args, resp_data):
    print(len(args), len(resp_data))
    result = dict([{
        codegen.spec_structures.Simple: self.__parse_simple_response,
        codegen.spec_structures.Repeat: self.__parse_repeat_response,
        }[arg.__class__](arg, resp) for (arg, resp) in zip(args, resp_data)])
    return result

  def __parse_simple_response(self, arg, simple_resp_data):
    return (arg.name, simple_resp_data)

  def __parse_repeat_response(self, arg, repeat_resp_data):
    print("REPEAT data: ", repeat_resp_data)
    result = dict([{
        codegen.spec_structures.Simple: self.__parse_simple_response,
        codegen.spec_structures.Group: self.__parse_group_response,
        }[arg.arg.__class__](arg.arg, data) for data in repeat_resp_data])
    print(result)
    return result

  def __parse_group_response(self, arg, group_resp_data):
    print("GROUP", arg, group_resp_data)
    return dict([("OMG", "WTF")])

  def send_command_sync(self, cmd_set_id, cmd_id, request_bytes):
    req_id = self.send_command_async(cmd_set_id, cmd_id, request_bytes)
    return self.get_reply(req_id)

  def send_command_async(self, cmd_set_id, cmd_id, request_bytes = []):
    '''Generate req_id, pack req data, and send cmd to jvm. Returns req_id'''
    req_id = self.generate_req_id()
    self.reqs_by_req_id[req_id] = (cmd_set_id, cmd_id, request_bytes)
    length = 11 + len(request_bytes)
    header = struct.pack(">IIBBB", length, req_id, 0, cmd_set_id, cmd_id)
    self.sock.send(header + request_bytes)
    return req_id

  def get_reply(self, req_id):
    '''Blocks until a reply is received for 'req_id'; returns err, reply'''
    while req_id not in self.replies_by_req_id:
      time.sleep(.05)
    err, reply = self.replies_by_req_id[req_id]
    if err != 0:
      raise Exception("JDWP error: %s" % err)
    return reply

  def disconnect(self):
    self.reader_thread.running = False
    self.sock.close();

  def report_event(self, req_id, event_packed):
    self.events.append((req_id, event_packed))
    if self.event_callback != None:
      self.event_callback(req_id, event_packed)

  def report_reply(self, req_id, reply_packed):
    self.replies_by_req_id[req_id] = (0, reply_packed)

  def report_error(self, req_id, err):
    self.replies_by_req_id[req_id] = (err, [])

  def receive(self):
    '''Reads header, flags, error code, and subsequent data from jdwp socket'''
    header = self.sock.recv(11);
    if len(header) == 0:
      return -1, 0, 0, ''
    length, req_id, flags, err = struct.unpack('>IIBH', header)
    remaining = length - 11
    msg = bytearray()
    while remaining > 0:
      chunk = self.sock.recv(min(remaining, 4096))
      msg.extend(chunk)
      remaining -= len(chunk)
    reply_packed = ''.join([chr(x) for x in msg])
    return req_id, flags, err, reply_packed

  def generate_req_id(self):
    result = self.next_req_id
    self.next_req_id += 1
    return result

  def spec_file_grammar(self, with_strings = False):
    open_paren = pp.Literal("(").suppress()
    close_paren = pp.Literal(")").suppress()
    spec_string = pp.OneOrMore(pp.dblQuotedString)
    if not with_strings:
      spec_string = spec_string.suppress()
    sexp = pp.Forward()
    string = spec_string | pp.Regex("([^()\s])+")
    sexp << ( string | pp.Group(open_paren + pp.ZeroOrMore(sexp) + close_paren) )
    return pp.OneOrMore(sexp)

EVENT_MAGIC_NUMBER = 0x4064
class ReaderThread(threading.Thread):
  '''Listens for, parses replies/events; forwards results to Jdwp'''
  def __init__(self, jdwp):
    super(ReaderThread, self).__init__(name="jdwp_reader")
    self.jdwp = jdwp
    self.setDaemon(True)
    self.running = True
    self.start()

  def run(self):
    while self.running:
      req_id, flags, err, reply_packed = self.jdwp.receive()
      if req_id == -1:
        continue
      if err != EVENT_MAGIC_NUMBER and err != 0:
        self.jdwp.report_error(req_id, err)
        continue
      if err == EVENT_MAGIC_NUMBER: # this is actually an event message
        self.jdwp.report_event(req_id, reply_packed)
        continue
      self.jdwp.report_reply(req_id, reply_packed)