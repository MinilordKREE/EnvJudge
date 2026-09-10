#!/bin/bash
# E3 layer 1 (PREREG9 @ 08a09b7): probe gate -> shared -> gate -> A -> gate -> G -> gate -> R -> h100 -> confirm -> tables
# Every stage is resumable; re-running this script after a reboot continues where it stopped.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
mkdir -p $L
gate() {
  ok=0
  while [ $ok -lt 3 ]; do
    if uv run python scripts/e3.py --stage probe >> $L/e3_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
    [ $ok -lt 3 ] && sleep 300
  done
}
run() {  # $1 stage  $2 concurrency
  gate
  echo "$1 start $(date -u +%FT%TZ)"
  uv run python scripts/e3.py --stage "$1" --concurrency "$2" >> "$L/e3_$1.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "CHAIN_FAILED $1 rc=$rc $(date -u +%FT%TZ)"; exit 1; fi
  echo "$1 done $(date -u +%FT%TZ) $(uv run python scripts/e3.py --stage spend 2>/dev/null | head -c 80)"
}
run shared 8
run A 4
run G 4
run R 4
run h100 8
run confirm 8
uv run python scripts/e3.py --stage tables >> $L/e3_tables.log 2>&1 || { echo "CHAIN_FAILED tables $(date -u +%FT%TZ)"; exit 1; }
echo "tables done $(date -u +%FT%TZ)"
touch runs/E3_DONE
echo E3_DONE
