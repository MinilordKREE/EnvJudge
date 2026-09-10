#!/bin/bash
# E2 step 1 (PREREG8-Z) in the pre-registered order: shared K16 -> Z -> Z-full -> G -> R -> confirmations -> tables
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
S="uv run python scripts/e2_step1.py"
run() { $S --stage "$@" > $L/e2_$1${2:+_$2}.log 2>&1 || { echo "CHAIN_FAILED $*"; exit 1; }; echo "$* done $(date -u +%FT%TZ)"; }
run confirm-shared --concurrency 8
run corpus-Z --concurrency 2
run zfull --concurrency 4
run corpus-G
run corpus-R
for arm in Z Zfull G R; do $S --stage confirm --arm $arm --concurrency 8 > $L/e2_confirm_$arm.log 2>&1 || { echo "CHAIN_FAILED confirm-$arm"; exit 1; }; echo "confirm-$arm done $(date -u +%FT%TZ)"; done
uv run python scripts/make_tables_e2.py > $L/e2_tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo E2_CHAIN_DONE
