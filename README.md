vimjdb
======

java debug support in vim (and oh so much more)vimjdb enables one to control a running jvm from inside of vim.
it is not a hack hobbled together from named pipes and jdb.

the jvm can be controlled by a remote program by way of their java platform
debugger architecture (jpda). a client connects on a user-selected port and
communicates according to the java debug wire protocol (jdwp). the jdwp is
specified in a lisp-like, machine-readable format, as well as in html format on
the web.
 
it is assumed from here on that you have a jvm running some program in debug
mode, listening for debugging clients on some port. we'll use 5005 as the
standard port in this document. the running jvm is referred to as the "target
jvm" and the program to be debugged as the "target program" (these may be used
somewhat interchangeably).

vimjdb has several components, then:
 + a vim plugin to a debug interface inside vim 
 + a debug "state server" to maintain state and handle asynchronous actions
   and push events, which can't be done in vim due to its single-threadedness
 + a set of protocol buffer and rpc service definitions wrapping the jdwp
 + an httprpc server implementing the rpc service interface, which communicates
   with the running target jvm

names of things:
 + vimjdb - the vim pluing
 + vjdss - the vim/jvm debug state server
 + jdwppb - the protobuf msg/rpc definitions (generated [mostly])
 + jdwprpc - the jdwp rpc server that implements jdwppb and talks to the jvm
             (also mostly generated)
