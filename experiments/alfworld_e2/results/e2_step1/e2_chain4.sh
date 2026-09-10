#!/bin/bash
# E2 step 1, chain v4: wait for the Qwen endpoint (3 clean probes, 5 min apart), then Z re-run (infra_error tasks),
# G (fresh), R, confirmations, tables, then Z-full reference last. Arms run one at a time.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
S="uv run python scripts/e2_step1.py"
ok=0
while [ $ok -lt 3 ]; do
  if uv run python scripts/endpoint_probe.py >> $L/e2_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
  [ $ok -lt 3 ] && sleep 300
done
run() { local name=$1; shift; $S --stage $name "$@" >> $L/e2_$name.log 2>&1 || { echo "CHAIN_FAILED $name"; exit 1; }; echo "$name done $(date -u +%FT%TZ)"; }
run corpus-Z --concurrency 1
run corpus-G
run corpus-R
for arm in Z G R; do $S --stage confirm --arm $arm --concurrency 6 > $L/e2_confirm_$arm.log 2>&1 || { echo "CHAIN_FAILED confirm-$arm"; exit 1; }; echo "confirm-$arm done $(date -u +%FT%TZ)"; done
uv run python scripts/make_tables_e2.py > $L/e2_tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo "tables (claim stages) done $(date -u +%FT%TZ)"
run zfull --concurrency 4
$S --stage confirm --arm Zfull --concurrency 6 > $L/e2_confirm_Zfull.log 2>&1 || { echo "CHAIN_FAILED confirm-Zfull"; exit 1; }
echo "confirm-Zfull done $(date -u +%FT%TZ)"
uv run python scripts/make_tables_e2.py > $L/e2_tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo E2_CHAIN_DONE
