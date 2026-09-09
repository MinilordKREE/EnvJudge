#!/bin/bash
# Round 1b items 1-2 (paid) + matched subsampling (free): corrected U banks -> placebo -> matched files -> evals for u2 + placebo
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
uv run python scripts/round1b.py --stage banks-u2 > $L/r1b_banks_u2.log 2>&1 || { echo CHAIN_FAILED banks-u2; exit 1; }
echo "banks-u2 done $(date -u +%FT%TZ)"
uv run python scripts/round1b.py --stage placebo > $L/r1b_placebo.log 2>&1 || { echo CHAIN_FAILED placebo; exit 1; }
echo "placebo done $(date -u +%FT%TZ)"
uv run python scripts/round1b.py --stage matched > $L/r1b_matched.log 2>&1 || { echo CHAIN_FAILED matched; exit 1; }
echo "matched files done $(date -u +%FT%TZ)"
uv run python scripts/round1b.py --stage jobs --group u2 && uv run python scripts/round1b.py --stage jobs --group placebo
python3 -c "import json; a=json.load(open('runs/r1-eval/jobs_u2.json')); b=json.load(open('runs/r1-eval/jobs_placebo.json')); json.dump(a+b, open('runs/r1-eval/jobs_item12.json','w'))"
uv run python scripts/round1.py --stage evals --workers 2 --concurrency 8 --jobs-file runs/r1-eval/jobs_item12.json >> $L/r1b_evals_item12.log 2>&1 || { echo CHAIN_FAILED evals-item12; exit 1; }
echo "evals item 1-2 done $(date -u +%FT%TZ)"
echo R1B_A_DONE
