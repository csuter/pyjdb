#!/bin/bash

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

if [[ $1 == 'clean' ]]
then
  rm -rf "$build_bin_dir"
  rm -rf "$build_gen_dir"
  rm -rf "$build_log_dir"
  exit 0
fi

rm -rf "$build_bin_dir/"*
rm -rf "$build_gen_dir/"*

mkdir -p "$build_bin_dir"
mkdir -p "$build_gen_dir"
mkdir -p "$build_log_dir"
mkdir -p tmp

stderr_log="$build_log_dir/$timestamp.build.sh.err"
stdout_log="$build_log_dir/$timestamp.build.sh.out"
latest_build_out=latest_build.out
latest_build_err=latest_build.err
exec > >(tee "$stdout_log")
exec 2> >(tee "$stderr_log")
ln -sf "$stderr_log" "$latest_build.err"
ln -sf "$stdout_log" "$latest_build_out"

log "Logging to $stdout_log and $stderr_log"

for i in $(find . -mindepth 2 -maxdepth 2 -name build.sh)
do
  log "*** Sourcing subbuild $i ***"
  cd "$dir" # ensure we're back where we started
  . $i
done

log "Done!"
