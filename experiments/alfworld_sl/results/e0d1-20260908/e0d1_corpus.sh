#!/bin/bash
# D1 (owner decision 1): released EnvRigger corpus on task ids 20-99 (E0 covered 0-19)
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
exec uv run python scripts/e0.py --stage corpus --run-id e0d1-20260908 --task-ids 20 100
