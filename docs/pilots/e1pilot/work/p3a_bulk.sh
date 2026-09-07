#!/usr/bin/env bash
cd /home/kree/work/EnvJudge/scratch/e1pilot
export PYTHONPATH=/home/kree/work/EnvJudge/scratch/eobs:/home/kree/work/EnvJudge/scratch/e1pilot ALFWORLD_DATA=/home/kree/eh_alfworld_data
for REP in 1 2 3; do
  echo "REP $REP START $(date -u +%H:%M)"
  ~/eobs_venv/bin/python e1/p3a.py --stage eval --rep $REP --n-id 30 --n-ood 30 --concurrency 6 2>&1 | grep -v -i -E "warn|it/s\]|Give Feedback|LiteLLM.Info|Initializing|Overall|Training|Evaluating with" | grep -E "FINAL|nobank|orig|Traceback|Error|\[P3a\]" | tail -n 12
  echo "REP $REP DONE $(date -u +%H:%M)"
done
~/eobs_venv/bin/python e1/p3a.py --stage tables --reps 1,2,3 2>&1 | tail -n 8
echo "P3A_DONE $(date -u +%H:%M)"
