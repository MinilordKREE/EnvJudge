#!/bin/bash
# Phase D: E2 zero side under aea v0.2 (10 tasks, cap 30, Qwen3-8B, proposer off) -> confirmations -> tables
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
ok=0
while [ $ok -lt 3 ]; do
  if uv run python scripts/e2_v02.py --stage probe >> $L/e2_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
  [ $ok -lt 3 ] && sleep 300
done
uv run python scripts/e2_v02.py --stage corpus --concurrency 1 > $L/e2v02_corpus.log 2>&1 || { echo "CHAIN_FAILED corpus"; exit 1; }
echo "corpus done $(date -u +%FT%TZ)"
uv run python scripts/e2_v02.py --stage confirm --concurrency 6 > $L/e2v02_confirm.log 2>&1 || { echo "CHAIN_FAILED confirm"; exit 1; }
echo "confirm done $(date -u +%FT%TZ)"
uv run python scripts/e2_v02.py --stage tables > $L/e2v02_tables.log 2>&1 || { echo "CHAIN_FAILED tables"; exit 1; }
echo E2V02_DONE
