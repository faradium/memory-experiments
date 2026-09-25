#!/bin/bash
set -u
if [ $# -eq 0 ]; then echo "usage: $0 <seed> [<seed> ...]" >&2; exit 1; fi
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

quota_pct() {
  cswap --status 2>/dev/null | grep '5h' | grep -oE '[0-9]+%' | head -1 | tr -d '%'
}

for SEED in "$@"; do
  while true; do
    P=$(quota_pct); P=${P:-100}
    if [ "$P" -le 15 ]; then break; fi
    echo "seed $SEED waiting: quota at ${P}% ($(date +%H:%M))"
    sleep 300
  done
  echo "=== launching seed $SEED at $(date +%H:%M) (quota $(quota_pct)%) ==="
  SYNTH_REP_OFFSET=$SEED bash realworld/run_tinydb.sh > logs/tinydb_seed${SEED}.log 2>&1
  echo "=== seed $SEED done at $(date +%H:%M) ==="
done
echo "CHAIN_DONE"
