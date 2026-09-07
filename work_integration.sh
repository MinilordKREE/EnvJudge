#!/bin/bash
cd /home/kree/work/EnvJudge
export PYTHONPATH=/home/kree/work/EnvJudge/src:/home/kree/work/EnvJudge ALFWORLD_DATA=$HOME/eh_alfworld_data
exec ~/eobs_venv/bin/python -m pytest tests/integration -m integration -q -x --no-header -p no:cacheprovider -o addopts="" 2>&1
