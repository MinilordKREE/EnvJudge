#!/bin/bash
cd /home/kree/work/EnvJudge
export PYTHONPATH=/home/kree/work/EnvJudge/src ALFWORLD_DATA=$HOME/eh_alfworld_data
exec ~/eobs_venv/bin/python scripts/aea_smoke.py --tasks 7 --cap-usd 3 --run-id smoke2-designer-20260907
