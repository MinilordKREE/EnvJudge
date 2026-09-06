#!/usr/bin/env bash
cd /home/kree/work/EnvJudge/scratch/e1pilot
export PYTHONPATH=/home/kree/work/EnvJudge/scratch/eobs:/home/kree/work/EnvJudge/scratch/e1pilot ALFWORLD_DATA=/home/kree/eh_alfworld_data
while pgrep -f "regime_map.py --stage bulk" >/dev/null; do sleep 60; done
echo "P1_BULK_DONE $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/regime_map.py --stage outputs 2>&1 | grep -v -i warn | tail -n 8
HIGH=$(~/eobs_venv/bin/python -c "import json; print(json.load(open('results/e1pilot/p1_summary.json'))['saturated+edge-high'])")
echo "saturated+edge-high=$HIGH"
if ~/eobs_venv/bin/python -c "import sys; sys.exit(0 if float('$HIGH') >= 0.15 else 1)"; then REG=qwen; else REG=pro_fallback; fi
echo "P2 regime: $REG  $(date -u +%H:%M)"
if ! pgrep -f "e1/watchdog.py" >/dev/null; then echo "watchdog missing; not starting P2"; exit 2; fi
~/eobs_venv/bin/python e1/p2_run.py --regime $REG 2>&1 | grep -v -i -E "warn|it/s\]|Initializing|Overall|Training" | grep "\[P2\]"
echo "P2_DONE $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/analyze.py f8080d4 d584098f2d7dfcd5f1152f18c93f595e380916bccabb454fff1100af6f3b5265 2>&1 | tail -n 2
echo "PIPELINE_DONE $(date -u +%H:%M)"
