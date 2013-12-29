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

PYTHONPATH="." python -m unittest -v pyjdb.pyjdb_test

ps aux \
  | grep java \
  | grep -v grep \
  | grep 'Test' \
  | awk '{print $2}' \
  | xargs -n1 kill -9
