
function! Vimjdb_Vjdss_SpawnIfNotAlive()
  python <<EOM
import vim, os, socket, time, sys
sys.path.append("build-bin/jdwprpc")
sys.path.append("build-bin")
import jdwp_pb2, protobuf.socketrpc, jdwp_impl

def check_vjdss_alive():
  try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 10002))
    sock.close()
    return True
  except socket.error:
    None
  return False

if not check_vjdss_alive():
  print("Relaunching vjdss")
  argv = ['build-bin/vjdss/vjdss.py']
  os.spawnvpe(os.P_NOWAIT, argv[0], argv, {'PYTHONPATH':'build-bin/jdwprpc:build-bin'})
  time.sleep(1)
  if not check_vjdss_alive():
    print("Can't connect to vjdss")
  else:
    print("vjdss looks good!")
else:
  print("vjdss looks good!")
EOM
endfunction

function! Vimjdb_Jdwprpc_SpawnIfNotAlive()
  python <<EOM
class PrintItCallback:
  def __init__(self, count):
    self._count = count

  def run(self, result):
    if result:
      print("jdwprpc looks good!")
    elif self._count > 0:
      print("Relaunching jdwprpc (%d more tries)!" % self._count)
      argv = ['tmp/test_server.py']
      os.spawnvpe(os.P_NOWAIT, argv[0], argv, {'PYTHONPATH':'build-bin/jdwprpc:build-bin'})
      time.sleep(1)
      channel = protobuf.socketrpc.channel.SocketRpcChannel("localhost",10001)
      controller = channel.newController()
      virtual_machine_service = jdwp_pb2.VirtualMachine_Stub(channel)  
      request = jdwp_pb2.VirtualMachine_Version_Request()
      virtual_machine_service.VirtualMachine_Version(controller, request, PrintItCallback(self._count-1))
    else:
      print("Giving up!")

channel = protobuf.socketrpc.channel.SocketRpcChannel("localhost",10001)
controller = channel.newController()
virtual_machine_service = jdwp_pb2.VirtualMachine_Stub(channel)  
request = jdwp_pb2.VirtualMachine_Version_Request()
virtual_machine_service.VirtualMachine_Version(controller, request, PrintItCallback(2))

EOM
endfunction

function! Vimjdb_start(port)
  echo "Vimjdb " . a:port
  " ensure vjdss is up
  if v:servername == ""
    echo "To use Vimjdb, please restart with an argument to --servername"
    return
 endif
  " ensure vjdss is up
  call Vimjdb_Vjdss_SpawnIfNotAlive()
  " ensure jdwprpc is up
  call Vimjdb_Jdwprpc_SpawnIfNotAlive()
endfunction

command! -nargs=1 Vimjdb :call Vimjdb_start(<args>)
