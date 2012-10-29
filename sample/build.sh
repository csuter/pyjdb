mkdir -p "$build_gen_dir/sample/classes"

log "Compiling java source code"
javac \
  -d "$build_gen_dir/sample/classes" \
  -sourcepath "sample/fib" \
  @<(find "sample/fib" -name '*.java')

log "Building jar"
mkdir -p "$build_bin_dir/sample"
cp "sample/fib/com/alltheburritos/debug/test/run.sh" "$build_bin_dir/sample"
cd "$build_gen_dir/sample/classes" && jar -cf "$build_bin_dir/sample/fib.jar" com/ && cd ../../
