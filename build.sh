#!/bin/bash
#
# vimjdb main build script.
#
# running
#  $ ./build.sh
# will create things as detailed below.
#
# running
#  $ ./build.sh clean
# will delete anything this build script creates
#
# creates build environment and subsequently sources any build.sh files found in
# directories that are adjacent to this build.sh file. note that they are
# sourced as part of this shell and not run in separate shells. any failures
# should kill the build and cause non-zero exit status to be returned.
#
# build environment consists of:
#  build-log/ - directory for build logs
#  build-gen/ - intermediate place for generated code and such
#  build-bin/ - actual, ostensibly distributable stuff
#  symlinks to latest build stdout/stderr logs
#
# see submodule build.sh files for details on what goes on there

dir=$(dirname "$0")
dir=$(cd "$dir" && pwd)

# die on non-zero exit
set -e

function log {
  echo "$(date +"[%Y-%m-%d %H:%M:%S]") $@"
}

log '\    / | |\    /|    o    | |   '
log ' \  /  | | \  / |    |  __| |__ '
log '  \/   | |  \/  |    | /  | |  \'
log ' build            \__| \__| |__/'

timestamp=$(date +%s)

build_bin_dir="$dir/build-bin"
build_gen_dir="$dir/build-gen"
build_log_dir="$dir/build-log"
latest_build_out=latest_build.out
latest_build_err=latest_build.err

if [[ $1 == 'clean' ]]
then
  rm -rf "$build_bin_dir"
  rm -rf "$build_gen_dir"
  rm -rf "$build_log_dir"
  rm -rf "$latest_build_out"
  rm -rf "$latest_build_err"
  find . -name '*.pyc' | xargs rm -rf
  log 'All clean!'
  exit 0
fi

rm -rf "$build_bin_dir/"*
rm -rf "$build_gen_dir/"*

mkdir -p "$build_bin_dir"
mkdir -p "$build_gen_dir"
mkdir -p "$build_log_dir"

stderr_log="$build_log_dir/$timestamp.build.sh.err"
stdout_log="$build_log_dir/$timestamp.build.sh.out"
exec > >(tee "$stdout_log")
exec 2> >(tee "$stderr_log")
ln -sf "$stderr_log" "$latest_build_err"
ln -sf "$stdout_log" "$latest_build_out"

log "Logging to $stdout_log and $stderr_log"

for i in $(find . -mindepth 2 -maxdepth 2 -name build.sh)
do
  log "*** Sourcing subbuild $i ***"
  cd "$dir" # ensure we're back where we started
  . $i
done

log "Done!"
