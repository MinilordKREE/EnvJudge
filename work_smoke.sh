#!/bin/bash
cd /home/kree/work/EnvJudge
export PYTHONPATH=/home/kree/work/EnvJudge/src ALFWORLD_DATA=$HOME/eh_alfworld_data
exec ~/eobs_venv/bin/python scripts/aea_smoke.py --tasks 6 1 9 --cap-usd 10 --run-id smoke-20260907
