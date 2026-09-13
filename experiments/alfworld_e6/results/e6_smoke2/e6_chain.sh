#!/usr/bin/env bash
# E6 smoke chain: search -> confirm -> tables. Log: runs/r1-logs/e6_chain2.log. Marker: runs/E6_SMOKE2_DONE.
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
log "search start"
uv run --no-sync python scripts/e6_smoke.py --stage search --concurrency 4; rc=$?
log "search exit $rc"
if [ "$rc" -ne 0 ]; then log "STOP after search"; exit "$rc"; fi
uv run --no-sync python scripts/e6_smoke.py --stage confirm --concurrency 4; rc=$?
log "confirm exit $rc"
uv run --no-sync python scripts/e6_smoke.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_smoke.py --stage spend
touch runs/E6_SMOKE2_DONE
log "E6 smoke done"
