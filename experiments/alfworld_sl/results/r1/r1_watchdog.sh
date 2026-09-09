#!/bin/bash
# Kill the Round-1 eval stage if the E1-SL total reaches the soft gate (external guard for the in-flight process).
cd /home/kree/work/EnvJudge
while pgrep -f "stage evals|r1b_chain|r1_chain" > /dev/null; do
  T=$(uv run python scripts/round1.py --stage spend 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["total"])')
  echo "$(date -u +%FT%TZ) total=$T"
  if python3 -c "import sys; sys.exit(0 if float('$T') >= 600.0 else 1)"; then
    echo "SOFT_GATE_HIT $T -> stopping evals"; pkill -f "stage eval-job"; pkill -f "stage evals"; touch runs/r1-eval/SOFT_GATE_HIT; exit 0
  fi
  sleep 600
done
echo WATCHDOG_EXIT
