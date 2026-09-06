#!/usr/bin/env bash
cd /home/kree/work/EnvJudge/scratch/e1pilot
export PYTHONPATH=/home/kree/work/EnvJudge/scratch/eobs:/home/kree/work/EnvJudge/scratch/e1pilot ALFWORLD_DATA=/home/kree/eh_alfworld_data
echo "INDUCE_START $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/p3a.py --stage induce --concurrency 4 2>&1 | grep -v -i -E "warn|Give Feedback|LiteLLM.Info" | grep -E "\[P3a\]|\[orig\]|Traceback|Error" 
echo "INDUCE_DONE $(date -u +%H:%M)"
echo "SMOKE_START $(date -u +%H:%M)"
~/eobs_venv/bin/python e1/p3a.py --stage eval --rep 0 --n-id 2 --n-ood 2 --concurrency 4 2>&1 | grep -v -i -E "warn|it/s\]|Give Feedback|LiteLLM.Info|Initializing|Overall|Training" | tail -n 20
echo "SMOKE_DONE $(date -u +%H:%M)"
