#!/usr/bin/env bash
# E6 LOW refalign chain: shared -> arms -> confirm -> tables -> spend. Log: runs/r1-logs/e6_refalign_chain.log. Marker: runs/E6_REFALIGN_DONE.
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
for stage in shared arms confirm; do
  log "$stage start"
  uv run --no-sync python scripts/e6_refalign.py --stage "$stage" --concurrency 4; rc=$?
  log "$stage exit $rc"
  if [ "$rc" -ne 0 ]; then log "STOP after $stage"; exit "$rc"; fi
done
uv run --no-sync python scripts/e6_refalign.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_refalign.py --stage spend
touch runs/E6_REFALIGN_DONE
log "E6 refalign done"
