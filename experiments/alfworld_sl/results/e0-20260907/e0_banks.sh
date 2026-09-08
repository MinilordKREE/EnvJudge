#!/bin/bash
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
exec uv run python scripts/e0.py --stage banks --run-id e0-20260907
