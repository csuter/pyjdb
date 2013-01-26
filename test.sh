#!/bin/bash
#
# vimjdb main test script.
#
# running
#  $ ./test.sh
# will build everything and run all tests as described below
#
# running
#  $ ./test.sh clean
# will delete anything this script creates
#
# first sources build.sh and subsequently sources any test.sh files found in
# directories that are adjacent to this file. note that they are sourced as
# part of this shell and not run in separate shells. any failures should cause
# the suite to fail and cause non-zero exit status to be returned.
#
# see submodule test.sh files for details on what goes on there

dir=$(dirname "$0")
dir=$(cd "$dir" && pwd)

# we will inherit all the build_*_dir definitions
. "$dir/build.sh"

log '\    / | |\    /|    o    | |   '
log ' \  /  | | \  / |    |  __| |__ '
log '  \/   | |  \/  |    | /  | |  \'
log ' test             \__| \__| |__/'

# we define our own build-test dir, though, and test log files
build_test_dir="$dir/build-test"
latest_test_out=latest_test.out
latest_test_err=latest_test.err

# to clean, run build clean and then clean our stuff
# maybe better to have build clean everything...?
if [[ $1 == 'clean' ]]
then
  "$dir/build.sh clean"
  rm -rf "$build_test_dir"
  rm -rf "$latest_test_out"
  rm -rf "$latest_test_err"
  exit 0
fi

rm -rf "$build_test_dir/"*

mkdir -p "$build_test_dir"

stderr_log="$build_log_dir/$timestamp.test.sh.err"
stdout_log="$build_log_dir/$timestamp.test.sh.out"
exec > >(tee "$stdout_log")
exec 2> >(tee "$stderr_log")
ln -sf "$stderr_log" "$latest_test_err"
ln -sf "$stdout_log" "$latest_test_out"

log "Logging to $stdout_log and $stderr_log"

testdirs='jdwprpc'

# we don't mind if a test script fails.
set +e

for i in $(find jdwprpc -name "*_test.py")
do
  log "*** Running python test $i ***"
  cd "$dir" # ensure we're back where we started
  PYTHONPATH="$build_bin_dir/jdwprpc" python2 $i -v
done

# cleanup any lingering java processes
killall java 2>/dev/null

log "Done!"
