#!/bin/bash
# Round 1b items 1-2 resume after the reboot: finish the 18 eval jobs (episode-level resume), then the 1b tables.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
uv run python scripts/round1.py --stage evals --workers 2 --concurrency 8 --jobs-file runs/r1-eval/jobs_item12.json >> $L/r1b_evals_item12.log 2>&1 || { echo CHAIN_FAILED evals-item12; exit 1; }
echo "evals item 1-2 done $(date -u +%FT%TZ)"
uv run python scripts/make_tables_1b.py > $L/tables_1b.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo R1B_B_DONE
