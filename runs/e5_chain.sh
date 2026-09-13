#!/bin/bash
# E5 (PREREG12): gate -> A2 (v0.2 midpoint start) -> A4 (v0.4 soft warm start) -> confirm -> tables. Cap USD 70.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
mkdir -p $L
gate() {
  ok=0
  while [ $ok -lt 3 ]; do
    if uv run python scripts/e3.py --stage probe >> $L/e5_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
    [ $ok -lt 3 ] && sleep 300
  done
}
step() {
  label=$1; shift
  echo "$label start $(date -u +%FT%TZ)"
  uv run python scripts/e5.py "$@" >> "$L/e5_$label.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "CHAIN_FAILED $label rc=$rc $(date -u +%FT%TZ)"; exit 1; fi
  echo "$label done $(date -u +%FT%TZ) $(uv run python scripts/e5.py --stage spend 2>/dev/null | head -c 50)"
}
gate
step A2 --stage A2
step A4 --stage A4
step confirm --stage confirm --concurrency 8
step tables --stage tables
touch runs/E5_DONE
echo E5_DONE
