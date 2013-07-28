import jdwpspec
import socket
import struct
import threading
import time

from pyjdb.internal import jdwpspec
from pyjdb.internal import serialization

class Jdwp:
  def __init__(self, jvm_port, event_callback=None):
    self.__reqs_by_req_id = dict()
    self.__replies_by_req_id = dict()
    self.__events = []
    self.__next_req_id = 1
    self.__event_callback = event_callback
    self.__spec = jdwpspec.ConstructFromRawSpecText()
    self.__service_types = {}
    self.__constant_types = {}
    # open socket to jvm
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.connect(('localhost', jvm_port))
    self.__id_sizes = None
    # handshake
    handshake = b'JDWP-Handshake'
    self.sock.send(handshake)
    data = self.sock.recv(len(handshake))
    if data != handshake:
      self.sock.close()
      raise Exception('Handshake failed')
    # kick off reader thread
    self.reader_thread = ReaderThread(self)
    # now that things are initialized, we need to fetch ID sizes before we make
    # any more calls (in case those calls require us to know the size of
    # variable-sized types like memory addresses)
    self.__id_sizes = self.VirtualMachine.IDSizes()

  class __AbstractService(object):
    def __init__(self, name, spec, jdwp):
      self.__methods = {}
      self.__name = name
      self.__spec = spec
      # TODO(cgs): refactor so this doesn't have to be passed in. it's awkward
      self.__jdwp = jdwp

    def __getattr__(self, method):
      if method in self.__methods:
        return self.__methods[method]
      if method not in self.__spec.CommandDictByCommandSetName(self.__name):
        raise Exception("No method %s in service %s" % (method, self.__name))
      self.__methods[method] =\
          lambda *args : self.__jdwp.CommandRequest(self.__name, method, args)
      return self.__methods[method]

  class __AbstractConstantSet(object):
    def __init__(self, name, spec):
      self.__constants = {}
      self.__name = name
      self.__spec = spec

    def __getattr__(self, constant):
      if constant in self.__constants:
        return self.__constants[constant]
      if not constant in self.__spec.ConstantDictByConstantSetName(self.__name):
        raise LookupError("No constant %s in set %s" % (constant, self.__name))
      self.__constants[constant] = \
          self.__spec.ConstantDictByConstantSetName(self.__name)[constant].value
      return self.__constants[constant]

  def __getattr__(self, attr):
    if self.__spec.HasCommandSet(attr):
      if attr not in self.__service_types:
        self.__service_types[attr] = type(
            attr,
            (self.__AbstractService,),
            {}
        )(attr, self.__spec, self)
      return self.__service_types[attr]
    if self.__spec.HasConstantSet(attr):
      if attr not in self.__constant_types:
        self.__constant_types[attr] = type(
            attr,
            (self.__AbstractConstantSet,),
            {}
        )(attr, self.__spec)
      return self.__constant_types[attr]
    raise LookupError("service/constant %s unknown" % attr)

  # this should be private but right now it's accessed by abstract service (see
  # todo above.
  def CommandRequest(self, service, method, request):
    out_descriptor = self.__spec.OutStructureForCommand(service, method)
    reply_descriptor = self.__spec.ReplyStructureForCommand(service, method)
    error_set_descriptor = self.__spec.ErrorSetStructureForCommand(service, method)
    request_bytes = serialization.SerializeRequest(out_descriptor,
                                                   self.__id_sizes,
                                                   request)
    response_bytes = self.__SendCommandSynchronously(service, method, request_bytes)
    return serialization.DeserializeReply(reply_descriptor,
                                          self.__id_sizes,
                                          response_bytes)

  def __SendCommandSynchronously(self, service, method, request_bytes):
    cmd_set_id = int(self.__spec.CommandSetByName(service)[0].partition('=')[2])
    cmd_id = int(self.__spec.CommandDictByCommandSetName(service)[method][0]\
        .partition('=')[2])
    req_id = self.__SendCommandAsynchronously(cmd_set_id, cmd_id, request_bytes)
    return self.__GetReplyByRequestId(req_id)

  def __SendCommandAsynchronously(self, cmd_set_id, cmd_id, request_bytes = []):
    '''Generate req_id, pack req data, and send cmd to jvm. Returns req_id'''
    req_id = self.__GenerateRequestId()
    self.__reqs_by_req_id[req_id] = (cmd_set_id, cmd_id, request_bytes)
    length = 11 + len(request_bytes)
    header = struct.pack(">IIBBB", length, req_id, 0, cmd_set_id, cmd_id)
    self.sock.send(header + request_bytes)
    return req_id

  def __GetReplyByRequestId(self, req_id):
    '''Blocks until a reply is received for 'req_id'; returns err, reply'''
    while req_id not in self.__replies_by_req_id:
      time.sleep(.05)
    err, reply = self.__replies_by_req_id[req_id]
    if err != 0:
      raise Exception("JDWP error: %s" % err)
    return reply

  def Disconnect(self):
    self.reader_thread.running = False
    self.sock.close();

  def ReportEvent(self, req_id, event_packed):
    self.__events.append((req_id, event_packed))
    if self.__event_callback != None:
      self.__event_callback(req_id, event_packed)

  def ReportReply(self, req_id, reply_packed):
    self.__replies_by_req_id[req_id] = (0, reply_packed)

  def ReportError(self, req_id, err):
    self.__replies_by_req_id[req_id] = (err, [])

  def Receive(self):
    '''Reads header, flags, error code, and subsequent data from jdwp socket'''
    header = self.sock.recv(11);
    if len(header) != 11:
      raise Exception(
          "Invalid header sent (len != 11); len = %d" % len(header));
    length, req_id, flags, err = struct.unpack('>IIBH', header)
    remaining = length - 11
    msg = bytearray()
    while remaining > 0:
      chunk = self.sock.recv(min(remaining, 4096))
      msg.extend(chunk)
      remaining -= len(chunk)
    reply_packed = ''.join([chr(x) for x in msg])
    return req_id, flags, err, reply_packed

  def __GenerateRequestId(self):
    result = self.__next_req_id
    self.__next_req_id += 1
    return result

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
      try:
        req_id, flags, err, reply_packed = self.jdwp.Receive()
      except Exception as e:
        print(e)
      if req_id == -1:
        continue
      if err != EVENT_MAGIC_NUMBER and err != 0:
        self.jdwp.ReportError(req_id, err)
        continue
      if err == EVENT_MAGIC_NUMBER: # this is actually an event message
        self.jdwp.ReportEvent(req_id, reply_packed)
        continue
      self.jdwp.ReportReply(req_id, reply_packed)
