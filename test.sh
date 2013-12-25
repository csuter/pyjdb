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

echo ' ___'
echo '|   \ \   /   o    | |   '
echo '|___/  \ /    |  __| |__ '
echo '|       /     | /  | |  \'
echo '| test /   \__| \__| |__/'

# we don't mind if a test script fails.
set +e

cd "$dir" # ensure we're back where we started

TEST_ARGS="pyjdb.tests.*"
if [[ -n "$1" ]]; then
  TEST_ARGS=$@
fi
PYTHONPATH="." python -m unittest -v $TEST_ARGS

ps aux \
  | grep java \
  | grep -v grep \
  | grep 'fib\.jar' \
  | awk '{print $2}' \
  | xargs -n1 kill -9
