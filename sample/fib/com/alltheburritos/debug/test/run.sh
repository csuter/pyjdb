#!/bin/bash

classpath=build-bin/sample/fib.jar
exec java \
  -cp $classpath \
  -Xrunjdwp:transport=dt_socket,server=y,suspend=n,address=5005 \
  com.alltheburritos.debug.test.TestProgram
