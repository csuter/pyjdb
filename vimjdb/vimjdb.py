import os, time
import protobuf.socketrpc
import jdwp_pb2

channel = protobuf.socketrpc.channel.SocketRpcChannel("localhost", 10001)
controller = channel.newController()
virtual_machine_service = jdwp_pb2.VirtualMachine_Stub(channel)  

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
  print("got %s" % callback.result)
  return callback.result

def VirtualMachine_Version():
  request = jdwp_pb2.VirtualMachine_Version_Request()
  return do_sync(virtual_machine_service.VirtualMachine_Version, request)

def VirtualMachine_Threads():
  """returns a tree of all thread groups and threads"""
  request = jdwp_pb2.VirtualMachine_AllThreads_Request()
  thread_ids = do_sync(virtual_machine_service.VirtualMachine_AllThreads, request)
  print(thread_ids)

def Jdwprpc_Spawn(jvm_port):
  argv = ['tmp/test_server.py', jvm_port]
  os.spawnvpe(os.P_NOWAIT, argv[0], argv, {'PYTHONPATH':'build-bin/jdwprpc:build-bin'})
