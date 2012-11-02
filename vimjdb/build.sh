
mkdir -p "$build_bin_dir/vimjdb/plugin"
log "Copying vimjdb plugin to build-bin"
cp "vimjdb/vimjdb.vim" "$build_bin_dir/vimjdb/plugin"
cp "vimjdb/vimjdb.py" "$build_bin_dir/vimjdb/plugin"
touch "$build_bin_dir/vimjdb/plugin/__init__.py"
