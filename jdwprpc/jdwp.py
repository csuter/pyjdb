"""
This package defines a single class for external use: Jdwp. Its constructor
requires a valid local jvm debug port and an event callback. On instantiation,
the Jdwp object connects to the target jvm, performs the obligatory handshake,
and is then ready to send commands and receive data and events. It also starts
a background thread, which reads and deserializes replies, errors, and events,
forwarding these to the appropriate handler method on Jdwp.

Author: Christopher Suter (cgs1019@gmail.com)
"""

import datautils
import jdwprpc
import socket
import struct
import threading
import time

class Jdwp:
  '''Provides a simple interface for interacting with a jdwp wire connection'''
  def __init__(self, port, event_callback):
    self.reqs_by_req_id = dict()
    self.replies_by_req_id = dict()
    self.events = []
    self.next_req_id = 0
    self.event_callback = event_callback

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.connect(('localhost', port))
    # handshake
    handshake = b'JDWP-Handshake'
    self.sock.send(handshake)
    data = self.sock.recv(len(handshake))
    if data != handshake:
      self.sock.close()
      raise Exception('Handshake failed')

    self.reader_thread = ReaderThread(self)

  def send_command_await_reply(self, cmd_set_id, cmd_id, req_unpacked = []):
    '''Defers to send_command_no_wait then returns the result of get_reply()'''
    req_id = self.send_command_no_wait(cmd_set_id, cmd_id, req_unpacked)
    return self.get_reply(req_id)

  def send_command_no_wait(self, cmd_set_id, cmd_id, req_unpacked = []):
    '''Generate req_id, pack req data, and send cmd to jvm. Returns req_id'''
    req_id = self.generate_req_id()
    self.reqs_by_req_id[req_id] = (cmd_set_id, cmd_id, req_unpacked)
    req_packed = datautils.pack_jdwp_request(
        cmd_set_id, cmd_id, req_unpacked)
    length = 11 + len(req_packed)
    header = struct.pack(">IIBBB", length, req_id, 0, cmd_set_id, cmd_id)
    self.sock.send(header + req_packed)
    return req_id

  def get_reply(self, req_id):
    '''Blocks until a reply is received for 'req_id'; returns err, reply'''
    while req_id not in self.replies_by_req_id:
      time.sleep(.05)
    return self.replies_by_req_id[req_id]

  def disconnect(self):
    self.reader_thread.running = False
    self.sock.close();

  # END EXTERNAL API; The following methods are for package-internal use only.

  def report_event(self, event_unpacked):
    self.events.append(event_unpacked)
    if self.event_callback != None:
      self.event_callback(event_unpacked)

  def report_reply(self, req_id, reply_unpacked):
    self.replies_by_req_id[req_id] = (0, reply_unpacked)

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
      self.handle_reply(req_id, flags, err, reply_packed)

  def handle_reply(self, req_id, flags, err, reply_packed):
    if req_id == -1:
      return
    if err == 0x4064: # this is actually an event message
      event_unpacked = datautils.unpack_jdwp_reply(64, 100, reply_packed)
      self.jdwp.report_event(event_unpacked)
      return
    if err != 0:
      self.jdwp.report_error(req_id, err)
      return
    cmd_set_id, cmd_id, _ = self.jdwp.reqs_by_req_id[req_id]
    self.jdwp.report_reply(
        req_id, datautils.unpack_jdwp_reply(cmd_set_id, cmd_id, reply_packed))
