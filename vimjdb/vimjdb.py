import jdwp_pb2
import os
import protobuf.socketrpc
import subprocess
import time

channel = protobuf.socketrpc.channel.SocketRpcChannel("localhost", 10001)
controller = channel.newController()
virtual_machine_service = jdwp_pb2.VirtualMachine_Stub(channel)  
event_request_service = jdwp_pb2.EventRequest_Stub(channel)

class ResultProviderCallback:
  def __init__(self):
    self.has_result = False
    self.result = None
  def run(self, result):
    self.result = result
    self.has_result = True

def do_sync(method, reqeuest):
  callback = ResultProviderCallback()
  method(controller, reqeuest, callback)
  while not callback.has_result:
    time.sleep(.1)
  return callback.result

def VirtualMachine_Version():
  request = jdwp_pb2.VirtualMachine_Version_Request()
  return do_sync(virtual_machine_service.VirtualMachine_Version, request)

def EventRequest_Set_Something():
  request = jdwp_pb2.EventRequest_Set_Request()
  request.eventKind = jdwp_pb2.EventKind_CLASS_LOAD
  request.suspendPolicy = jdwp_pb2.SuspendPolicy_EVENT_THREAD
  return do_sync(event_request_service.EventRequest_Set, request)

def Jdwprpc_Spawn(jvm_port):
  cmd = "%s/build-bin/jdwprpc/jdwprpc.sh" % os.getcwd()
  subprocess.Popen([cmd, "10001", "5005"])
  time.sleep(1)
