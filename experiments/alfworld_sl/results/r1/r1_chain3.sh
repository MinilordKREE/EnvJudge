#!/bin/bash
# Round 1 chain v3: resume evals (episode-level), then tables.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
uv run python scripts/round1.py --stage evals --workers 2 --concurrency 8 >> $L/evals.log 2>&1 || { echo CHAIN_FAILED evals; exit 1; }
echo "evals done $(date -u +%FT%TZ)"
uv run python scripts/make_tables.py > $L/tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo R1_CHAIN_DONE
