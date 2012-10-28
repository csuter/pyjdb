#!/usr/bin/python2

import jdwp_pb2
import protobuf.socketrpc
import socket
import sys

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("localhost", 10002))
s.listen(1)

def init(vim_servername, jvm_port):
  classes_response = []

  hostname = "localhost"
  port = 10001

  channel = protobuf.socketrpc.channel.SocketRpcChannel(hostname,port)
  controller = channel.newController()

  virtual_machine_service = jdwp_pb2.VirtualMachine_Stub(channel)	
  event_request_service = jdwp_pb2.EventRequest_Stub(channel)
  event_service = jdwp_pb2.Event_Stub(channel)

  class PrintItCallback:
    def run(self, result):
      print("result: %s" % result)

  request = jdwp_pb2.VirtualMachine_AllThreads_Request()
  virtual_machine_service.VirtualMachine_AllClasses(controller, request, PrintItCallback())

while 1:
  conn, addr = s.accept()
  data = conn.recv(4096)
  datastr = data.decode('utf-8')
  parts = datastr.split(":")
  (cmd, rest) = (parts[0], parts[1:])
  #{'init':init}[cmd](rest[0], rest[1])
  conn.close()
