#!/usr/bin/env bash
# Run arms in independent lanes; each arm: smoke (3 tasks x 2 rollouts) then full run. Stops the lane on budget stop (exit 3).
set -u
cd "$(dirname "$0")"
PY=/home/kree/work/switchHarness/.venv/bin/python
export PYTHONPATH=.
LANE="$1"; shift
for ARM in "$@"; do
  echo "[$(date -u +%FT%TZ)] lane $LANE: smoke $ARM"
  $PY -m emin.rollouts smoke --arm "$ARM" || { echo "lane $LANE: smoke $ARM failed/stopped (exit $?)"; exit 3; }
  echo "[$(date -u +%FT%TZ)] lane $LANE: run $ARM"
  $PY -m emin.rollouts run --arm "$ARM" || { echo "lane $LANE: run $ARM failed/stopped (exit $?)"; exit 3; }
done
echo "[$(date -u +%FT%TZ)] lane $LANE done"
