#!/usr/bin/env bash
# E6 LOW assistive Rules chain: shared (task pool 4 x 4) -> arms A and B in parallel (8 each) -> confirm (16) -> tables
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
log "shared start"
uv run --no-sync python scripts/e6_assist.py --stage shared --concurrency 4 --task-concurrency 4; rc=$?
log "shared exit $rc"
if [ "$rc" -ne 0 ]; then log "STOP after shared"; exit "$rc"; fi
log "arms start"
uv run --no-sync python scripts/e6_assist.py --stage arms --arm A --concurrency 8 > runs/r1-logs/e6_ar_armA.log 2>&1 &
pa=$!
uv run --no-sync python scripts/e6_assist.py --stage arms --arm B --concurrency 8 > runs/r1-logs/e6_ar_armB.log 2>&1 &
pb=$!
wait $pa; ra=$?
wait $pb; rb=$?
log "arms exit A=$ra B=$rb"
if [ "$ra" -ne 0 ] || [ "$rb" -ne 0 ]; then log "STOP after arms"; exit 1; fi
log "confirm start"
uv run --no-sync python scripts/e6_assist.py --stage confirm --concurrency 16; rc=$?
log "confirm exit $rc"
uv run --no-sync python scripts/e6_assist.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_assist.py --stage spend
touch runs/E6_AR_DONE
log "E6 assistive rules done"
