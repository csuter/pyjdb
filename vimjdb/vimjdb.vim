python <<EOM
import sys, vim
sys.path.append('build-bin/')
sys.path.append('build-bin/jdwprpc')
sys.path.append('build-bin/vimjdb/plugin')
import vimjdb
EOM

function! Vimjdb_start(jvm_port)
  if v:servername == ""
    echo "To use Vimjdb, please restart with an argument to --servername"
    return
  endif
  " ensure jdwprpc is up
  py vimjdb.Jdwprpc_Spawn(vim.eval('a:jvm_port'))
  py print(vimjdb.VirtualMachine_Version())
endfunction

command! -nargs=1 Vimjdb :call Vimjdb_start(<args>)
