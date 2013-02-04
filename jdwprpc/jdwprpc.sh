#!/bin/bash

exec > /tmp/jdwprpc.out
exec 2> /tmp/jdwprpc.err

dir=$(dirname "$0")
dir=$(cd "$dir" && pwd)

echo "dir: $dir"

cd "$dir" 

echo PID: $PID

echo "executing: /usr/bin/python2 jdwprpc.py $@"
exec /usr/bin/python2 jdwprpc.py $@
