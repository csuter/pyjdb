#!/bin/bash


rm -rf .classes
mkdir -p .classes
javac \
  -d ".classes" \
  -sourcepath "java_sample/fib" \
  @<(find "java_sample/fib" -name '*.java')

cd ".classes" && jar -cf "../fib.jar" com/ && cd ..
