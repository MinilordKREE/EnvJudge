#!/bin/bash
# Round 1 chain: A after O; A-ex after G/G+; A+H after A; confirmations; banks; evals; tables.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
S="uv run python scripts/round1.py"
wait_for() { until grep -q "$1" "$2" 2>/dev/null; do if [ -n "$3" ] && ! pgrep -f "$3" >/dev/null; then echo "WAIT_FAILED $2"; exit 1; fi; sleep 30; done; }
echo "chain start $(date -u +%FT%TZ)"
wait_for '"stage": "corpus-O", "done": true' $L/corpus-O.log "stage corpus-O"
$S --stage corpus-A --concurrency 2 > $L/corpus-A.log 2>&1 &
PA=$!
wait_for 'PHASE1_DONE' $L/phase1.log "r1_launch_phase1"
$S --stage corpus-Aex --concurrency 2 > $L/corpus-Aex.log 2>&1 &
PX=$!
wait $PA; RA=$?; echo "corpus-A rc=$RA"; [ $RA -eq 0 ] || { echo CHAIN_FAILED corpus-A; exit 1; }
$S --stage aplush > $L/aplush.log 2>&1 || { echo CHAIN_FAILED aplush; exit 1; }
wait $PX; RX=$?; echo "corpus-Aex rc=$RX"; [ $RX -eq 0 ] || { echo CHAIN_FAILED corpus-Aex; exit 1; }
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
