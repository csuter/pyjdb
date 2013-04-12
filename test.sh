#!/bin/bash
#
# vimjdb main test script.
#
# running
#  $ ./test.sh
# will run all tests as described below
#
# running
#  $ ./test.sh clean
# will delete anything this script creates
#
# sources any test.sh files found in directories that are adjacent to this file.
# note that they are sourced as part of this shell and not run in separate
# shells. any failures should cause the suite to fail and cause non-zero exit
# status to be returned.
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

for i in $(find jdwprpc -name "*_test.py" | grep jdwp_test)
do
  cd "$dir" # ensure we're back where we started
  PYTHONPATH="jdwprpc" python2 $i -v
done

# cleanup any lingering java processes
killall java 2>/dev/null
