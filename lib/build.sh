
# proto compilation
log "Compiling protobuf proto defintions"
mkdir -p "$build_gen_dir/google/protobuf"
protoc \
  --proto_path=lib \
  --python_out=$build_gen_dir \
  lib/google/protobuf/descriptor.proto \

log "Compiling rpc proto defintions"
mkdir -p "$build_gen_dir/protobuf/socketrpc"
protoc \
  --proto_path=lib \
  --python_out=$build_gen_dir \
  lib/protobuf/socketrpc/rpc.proto \

cp -r lib/google "$build_bin_dir/jdwprpc"
cp -r lib/protobuf "$build_bin_dir/jdwprpc"

cp -r "$build_gen_dir/google/"* "$build_bin_dir/jdwprpc/google"
cp -r "$build_gen_dir/protobuf/"* "$build_bin_dir/jdwprpc/protobuf"
