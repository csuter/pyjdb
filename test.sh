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
# runs build.sh and subsequently sources any test.sh files found in directories
# that are adjacent to this file. note that they are sourced as part of this
# shell and not run in separate shells. any failures should cause the suite to
# fail and cause non-zero exit status to be returned.
#
# see submodule test.sh files for details on what goes on there

dir=$(dirname "$0")
dir=$(cd "$dir" && pwd)

# die on non-zero exit
set -e

function log {
  echo "$(date +"[%Y-%m-%d %H:%M:%S]") $@"
}

timestamp=$(date +%s)

build_bin_dir="$dir/build-bin"
build_gen_dir="$dir/build-gen"
build_log_dir="$dir/build-log"
build_test_dir="$dir/build-test"
latest_test_out=latest_test.out
latest_test_err=latest_test.err

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

for i in $(find . -mindepth 2 -maxdepth 2 -name build.sh)
do
  log "*** Sourcing subbuild $i ***"
  cd "$dir" # ensure we're back where we started
  . $i
done

log "Done!"
