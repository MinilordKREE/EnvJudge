#!/bin/bash
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
exec uv run python scripts/e0.py --stage corpus --run-id e0-20260907 --n-tasks 20
