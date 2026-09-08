#!/bin/bash
# usage: runs/e0_eval.sh <seed> [concurrency]
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
exec uv run python scripts/e0.py --stage eval --run-id e0-20260907 --seeds "$1" --concurrency "${2:-8}"
