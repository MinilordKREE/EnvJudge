#!/bin/bash
# E2 step 1, chain v2: claim-bearing stages first (Z -> G -> R -> confirmations -> tables), Z-full reference last
# (the per-episode cost is ~4x the pre-registered projection; the USD 90 cap must cover Z1/Z2 first).
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
S="uv run python scripts/e2_step1.py"
while pgrep -f "e2_step1.py --stage confirm-shared" > /dev/null; do sleep 20; done
echo "confirm-shared done $(date -u +%FT%TZ)"
run() { local name=$1; shift; $S --stage $name "$@" > $L/e2_$name.log 2>&1 || { echo "CHAIN_FAILED $name"; exit 1; }; echo "$name done $(date -u +%FT%TZ)"; }
run corpus-Z --concurrency 2
run corpus-G
run corpus-R
for arm in Z G R; do $S --stage confirm --arm $arm --concurrency 8 > $L/e2_confirm_$arm.log 2>&1 || { echo "CHAIN_FAILED confirm-$arm"; exit 1; }; echo "confirm-$arm done $(date -u +%FT%TZ)"; done
uv run python scripts/make_tables_e2.py > $L/e2_tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo "tables (claim stages) done $(date -u +%FT%TZ)"
run zfull --concurrency 4
$S --stage confirm --arm Zfull --concurrency 8 > $L/e2_confirm_Zfull.log 2>&1 || { echo "CHAIN_FAILED confirm-Zfull"; exit 1; }
echo "confirm-Zfull done $(date -u +%FT%TZ)"
uv run python scripts/make_tables_e2.py > $L/e2_tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo E2_CHAIN_DONE
