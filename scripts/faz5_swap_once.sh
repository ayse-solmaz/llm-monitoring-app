#!/bin/sh
# Surgical MLC weight swap. Run inside alpine with:
#   -v llm-monitoring-app_mlc-model:/data
#   -v <host>/backups/new-weights:/new:ro
# Does NOT touch gemma-cpu.so, mlc-chat-config.json, or tokenizer files.
set -e

echo "BEFORE shard count: $(ls /data/params_shard_*.bin 2>/dev/null | wc -l)"
SO_BEFORE=$(md5sum /data/gemma-cpu.so | awk '{print $1}')
CFG_BEFORE=$(md5sum /data/mlc-chat-config.json | awk '{print $1}')
echo "so_before=$SO_BEFORE"
echo "cfg_before=$CFG_BEFORE"

rm -f /data/params_shard_*.bin /data/ndarray-cache.json /data/tensor-cache.json
cp /new/params_shard_*.bin /data/

if [ -f /new/tensor-cache.json ]; then
  cp /new/tensor-cache.json /data/tensor-cache.json
  cp /new/tensor-cache.json /data/ndarray-cache.json
elif [ -f /new/ndarray-cache.json ]; then
  cp /new/ndarray-cache.json /data/ndarray-cache.json
  cp /new/ndarray-cache.json /data/tensor-cache.json
else
  echo "ERROR: no cache json in /new"
  exit 1
fi

echo "AFTER shard count: $(ls /data/params_shard_*.bin | wc -l)"
ls -la /data/gemma-cpu.so /data/mlc-chat-config.json /data/tokenizer.json \
  /data/ndarray-cache.json /data/tensor-cache.json

SO_AFTER=$(md5sum /data/gemma-cpu.so | awk '{print $1}')
CFG_AFTER=$(md5sum /data/mlc-chat-config.json | awk '{print $1}')
echo "so_after=$SO_AFTER"
echo "cfg_after=$CFG_AFTER"

test "$SO_AFTER" = "$SO_BEFORE"
test "$CFG_AFTER" = "$CFG_BEFORE"
# both caches must be identical after swap
test "$(md5sum /data/ndarray-cache.json | awk '{print $1}')" = \
     "$(md5sum /data/tensor-cache.json | awk '{print $1}')"

echo SWAP_OK
