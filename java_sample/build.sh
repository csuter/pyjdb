#!/bin/bash

dir=$(cd "$(dirname $0)" && pwd)

cd "$dir"
rm -rf .classes
mkdir -p .classes
javac \
  -d ".classes" \
  -sourcepath "./fib" \
  @<(find "./fib" -name '*.java')

cd ".classes" && jar -cf "../fib.jar" com/ && cd ..
