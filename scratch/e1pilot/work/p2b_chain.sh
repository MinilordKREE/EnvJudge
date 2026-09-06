#!/usr/bin/env bash
cd /home/kree/work/EnvJudge/scratch/e1pilot
export PYTHONPATH=/home/kree/work/EnvJudge/scratch/eobs:/home/kree/work/EnvJudge/scratch/e1pilot ALFWORLD_DATA=/home/kree/eh_alfworld_data
while ! grep -q "P3A_DONE" work/p3a_bulk.log 2>/dev/null; do sleep 60; done
echo "P2B_START $(date -u +%H:%M)"
if ! ps -eo args | grep -q "[e]1/watchdog.py"; then echo "watchdog missing; aborting P2b"; exit 2; fi
~/eobs_venv/bin/python e1/p2b_run.py --secondary 2>&1 | grep -v -i -E "warn|it/s\]|Initializing|Overall|Training" | grep -E "\[P2b\]|Traceback|Error"
echo "P2B_DONE $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/analyze_p2b.py 2>&1 | tail -n 12
echo "P2B_ANALYZED $(date -u +%H:%M)"
