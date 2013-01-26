#!/bin/bash

classpath=build-bin/sample/fib.jar
exec >/dev/null
exec 2>/dev/null
exec java \
  -cp $classpath \
  -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005 \
  com.alltheburritos.vimjdb.test.TestProgram
