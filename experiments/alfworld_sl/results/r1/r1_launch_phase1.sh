#!/bin/bash
# Round 1 phase 1: G, G+ (released orchestrator, 5 episodes each) and O (8 episodes) in parallel
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
uv run python scripts/round1.py --stage corpus-G     > runs/r1-logs/corpus-G.log 2>&1 &
uv run python scripts/round1.py --stage corpus-Gplus > runs/r1-logs/corpus-Gplus.log 2>&1 &
uv run python scripts/round1.py --stage corpus-O     > runs/r1-logs/corpus-O.log 2>&1 &
wait
echo PHASE1_DONE
