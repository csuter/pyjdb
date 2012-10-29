mkdir -p "$build_gen_dir/jdwprpc"

# code generation
log "Generating JDWP proto definitions and implementation"
cp -r jdwprpc/codegen "$build_gen_dir/jdwprpc/"
cp -r jdwprpc/jdwp_impl/jdwp_impl.py "$build_gen_dir/jdwprpc/"
"$build_gen_dir/jdwprpc/codegen/generate_all_code.py" "$dir"

log "Compiling jdwp proto defintions"
protoc \
  --proto_path=$build_gen_dir/jdwprpc \
  --python_out=$build_gen_dir/jdwprpc \
  $build_gen_dir/jdwprpc/jdwp.proto \

mkdir -p "$build_bin_dir/jdwprpc"
cp "$build_gen_dir/jdwprpc/jdwp.proto" "$build_bin_dir/jdwprpc"
cp "$build_gen_dir/jdwprpc/jdwp_impl.py" "$build_bin_dir/jdwprpc"
cp "$build_gen_dir/jdwprpc/jdwp_pb2.py" "$build_bin_dir/jdwprpc"
cp "$build_gen_dir/jdwprpc/jdwprpc.py" "$build_bin_dir/jdwprpc"
