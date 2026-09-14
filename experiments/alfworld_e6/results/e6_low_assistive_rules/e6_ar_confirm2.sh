#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
log "confirm2 start"
uv run --no-sync python scripts/e6_assist.py --stage confirm --concurrency 16; rc=$?
log "confirm exit $rc"
uv run --no-sync python scripts/e6_assist.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_assist.py --stage spend
touch runs/E6_AR_DONE2
log "confirm2 done"
