#!/usr/bin/env bash
# E6 LOW oracle actuator ceiling: endpoint probe -> arms O1 and O2 in parallel (8 each) -> confirm (16) -> tables -> spend
set -u
cd "$(dirname "$0")/.."
log() { echo "$1 $(date -u +%FT%TZ)"; }
log "probe start"
uv run --no-sync python scripts/e6_oracle.py --stage probe_endpoint; rc=$?
log "probe exit $rc"
if [ "$rc" -ne 0 ]; then log "STOP after probe"; exit "$rc"; fi
log "arms start"
uv run --no-sync python scripts/e6_oracle.py --stage arms --arm O1 --concurrency 8 > runs/r1-logs/e6_oa_armO1.log 2>&1 &
p1=$!
uv run --no-sync python scripts/e6_oracle.py --stage arms --arm O2 --concurrency 8 > runs/r1-logs/e6_oa_armO2.log 2>&1 &
p2=$!
wait $p1; r1=$?
wait $p2; r2=$?
log "arms exit O1=$r1 O2=$r2"
if [ "$r1" -ne 0 ] || [ "$r2" -ne 0 ]; then log "STOP after arms"; exit 1; fi
log "confirm start"
uv run --no-sync python scripts/e6_oracle.py --stage confirm --concurrency 16; rc=$?
log "confirm exit $rc"
uv run --no-sync python scripts/e6_oracle.py --stage tables; log "tables exit $?"
uv run --no-sync python scripts/e6_oracle.py --stage spend
touch runs/E6_OA_DONE
log "E6 oracle actuator done"
