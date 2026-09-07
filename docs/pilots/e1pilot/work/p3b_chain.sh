#!/usr/bin/env bash
cd /home/kree/work/EnvJudge/scratch/e1pilot
export PYTHONPATH=/home/kree/work/EnvJudge/scratch/eobs:/home/kree/work/EnvJudge/scratch/e1pilot ALFWORLD_DATA=/home/kree/eh_alfworld_data
echo "P3B_BANKS_START $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/p3b.py --stage banks --concurrency 4 2>&1 | grep -v -i -E "warn|Give Feedback|LiteLLM.Info" | grep -E "\[P3b\]|\[ours\]|\[orig_m\]|Traceback|Error"
echo "P3B_BANKS_DONE $(date -u +%H:%M)"
if ! ps -eo args | grep -q "[e]1/watchdog.py"; then echo "watchdog missing; aborting P3b eval"; exit 2; fi
for REP in 1 2 3; do
  echo "P3B REP $REP START $(date -u +%H:%M)"
  ~/eobs_venv/bin/python e1/p3b.py --stage eval --rep $REP --concurrency 6 2>&1 | grep -v -i -E "warn|it/s\]|Give Feedback|LiteLLM.Info|Initializing|Overall|Training|Evaluating with" | grep -E "FINAL|orig_m|ours|Traceback|Error|\[P3b\]" | tail -n 10
  echo "P3B REP $REP DONE $(date -u +%H:%M)"
done
~/eobs_venv/bin/python e1/p3b.py --stage tables --reps 1,2,3 2>&1 | tail -n 16
echo "P3B_DONE $(date -u +%H:%M)"
