#!/bin/bash
# E3b (PREREG10): aea v0.3's A arm on the E3 task set; G, R, H100, shared K16 and E3-SL's other cells reused.
# probe gate -> A_v0.3 search -> confirmations -> e3b_layer1.md -> banks -> matched -> gate -> SL evals (A only) -> e3b_sl.md
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
mkdir -p $L
gate() {
  ok=0
  while [ $ok -lt 3 ]; do
    if uv run python scripts/e3.py --stage probe >> $L/e3b_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
    [ $ok -lt 3 ] && sleep 300
  done
}
step() {  # $1 label, $2 script, rest = args
  label=$1; script=$2; shift 2
  echo "$label start $(date -u +%FT%TZ)"
  uv run python "$script" --variant e3b "$@" >> "$L/e3b_$label.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "CHAIN_FAILED $label rc=$rc $(date -u +%FT%TZ)"; exit 1; fi
  echo "$label done $(date -u +%FT%TZ) $(uv run python scripts/e3.py --variant e3b --stage spend 2>/dev/null | head -c 60)"
}
gate
step A scripts/e3.py --stage A --concurrency 4
step confirm scripts/e3.py --stage confirm --concurrency 8
step tables scripts/e3.py --stage tables
step banks-A scripts/e3sl.py --stage banks --arm A
step matched scripts/e3sl.py --stage matched
gate
step evals-matched scripts/e3sl.py --stage evals --group matched
step evals-full scripts/e3sl.py --stage evals --group full
step evals-cascade scripts/e3sl.py --stage evals --group cascade
step sl-tables scripts/e3sl.py --stage tables
touch runs/E3B_DONE
echo E3B_DONE
