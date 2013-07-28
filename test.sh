#!/bin/bash
#
# pyjdb main test script.
#
# Usage:
#  $ ./test.sh
# will run all tests found source tree
#
# see submodule test.sh files for details on what goes on there

dir=$(dirname "$0")
dir=$(cd "$dir" && pwd)

echo '\    / | |\    /|    o    | |   '
echo ' \  /  | | \  / |    |  __| |__ '
echo '  \/   | |  \/  |    | /  | |  \'
echo ' test             \__| \__| |__/'

# we don't mind if a test script fails.
set +e

for i in $(find test -name "*_test.py")
do
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src" python2 $i -v
  cd "$dir" # ensure we're back where we started
done
