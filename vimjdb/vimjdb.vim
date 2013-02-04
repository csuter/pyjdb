python <<EOM
import sys, vim
sys.path.append('build-bin/jdwprpc')
sys.path.append('build-bin/vimjdb/plugin')
import vimjdb
EOM

function! Vimjdb_start(jvm_port)
  " ensure jdwprpc is up
  py vimjdb.Jdwprpc_Spawn(vim.eval('a:jvm_port'))
endfunction

command! -nargs=1 Vimjdb :call Vimjdb_start(<args>)
