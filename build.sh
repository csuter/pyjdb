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

rm -rf "$build_bin_dir/"*
rm -rf "$build_gen_dir/"*

mkdir -p "$build_bin_dir"
mkdir -p "$build_gen_dir"
mkdir -p "$build_log_dir"

stderr_log="$build_log_dir/$timestamp.build.sh.err"
stdout_log="$build_log_dir/$timestamp.build.sh.out"
last_err=last_err
last_out=last_out
exec > >(tee "$stdout_log")
exec 2> >(tee "$stderr_log")
ln -sf "$stderr_log" "$last_err"
ln -sf "$stdout_log" "$last_out"

log "Logging to $stdout_log and $stderr_log"

for i in $(find . -mindepth 2 -maxdepth 2 -name build.sh)
do
  log "*** Sourcing subbuild $i ***"
  cd "$dir" # ensure we're back where we started
  . $i
done

log "Done!"
