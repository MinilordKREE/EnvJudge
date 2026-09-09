#!/bin/bash
# Round 1 chain (v2, after the A-ex manifest fix): A+H after A; confirmations after A and A-ex; banks; evals; tables.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
S="uv run python scripts/round1.py"
wait_for() { until grep -q "$1" "$2" 2>/dev/null; do if ! pgrep -f "$3" >/dev/null; then echo "WAIT_FAILED $2"; exit 1; fi; sleep 30; done; }
echo "chain2 start $(date -u +%FT%TZ)"
wait_for '"stage": "corpus-A", "done": true' $L/corpus-A.log "stage corpus-A "
$S --stage aplush > $L/aplush.log 2>&1 || { echo CHAIN_FAILED aplush; exit 1; }
echo "aplush done $(date -u +%FT%TZ)"
wait_for '"stage": "corpus-Aex", "done": true' $L/corpus-Aex.log "stage corpus-Aex"
for arm in shared R G Gplus A Aex AplusH; do
  $S --stage confirm --arm $arm --concurrency 8 > $L/confirm-$arm.log 2>&1 || { echo CHAIN_FAILED confirm-$arm; exit 1; }
  echo "confirm-$arm done $(date -u +%FT%TZ)"
done
$S --stage banks > $L/banks.log 2>&1 || { echo CHAIN_FAILED banks; exit 1; }
echo "banks done $(date -u +%FT%TZ)"
$S --stage evals --workers 2 --concurrency 8 > $L/evals.log 2>&1 || { echo CHAIN_FAILED evals; exit 1; }
echo "evals done $(date -u +%FT%TZ)"
uv run python scripts/make_tables.py > $L/tables.log 2>&1 || { echo CHAIN_FAILED tables; exit 1; }
echo R1_CHAIN_DONE
