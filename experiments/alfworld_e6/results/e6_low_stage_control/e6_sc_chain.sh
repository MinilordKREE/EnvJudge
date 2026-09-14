#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
for stage in shared arms confirm; do
  log "$stage start"
  uv run --no-sync python scripts/e6_stage_control.py --stage "$stage" --concurrency 4; rc=$?
  log "$stage exit $rc"
  if [ "$rc" -ne 0 ]; then log "STOP after $stage"; exit "$rc"; fi
done
uv run --no-sync python scripts/e6_stage_control.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_stage_control.py --stage spend
touch runs/E6_SC_DONE
log "E6 stage control done"
