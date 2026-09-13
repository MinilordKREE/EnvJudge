#!/bin/bash
# E4 (PREREG11 + amendment 1): gate -> full-bank rows -> item-matched rows -> count-matched g3 -> tables. Cap USD 130.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
mkdir -p $L
gate() {
  ok=0
  while [ $ok -lt 3 ]; do
    if uv run python scripts/e3.py --stage probe >> $L/e4_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
    [ $ok -lt 3 ] && sleep 300
  done
}
step() {
  label=$1; shift
  echo "$label start $(date -u +%FT%TZ)"
  uv run python scripts/e4.py "$@" >> "$L/e4_$label.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "CHAIN_FAILED $label rc=$rc $(date -u +%FT%TZ)"; exit 1; fi
  echo "$label done $(date -u +%FT%TZ) $(uv run python scripts/e4.py --stage spend 2>/dev/null | head -c 50)"
}
gate
step evals-full --stage evals --group full
step evals-matched --stage evals --group matched
step evals-count --stage evals --group count
step tables --stage tables
touch runs/E4_DONE
echo E4_DONE
