#!/bin/bash
# E3-SL (PREREG9 Addendum SL @ f9623e2): placebo -> N + placebo evals -> [E3 shared done] O banks
# -> [E3 confirm done] A, G, R banks (+ cascades) -> matched -> matched evals -> full -> cascade -> tables.
# Every stage is resumable; re-run after a reboot to continue. Exit 2 = the USD 180 hard stop.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
L=runs/r1-logs
mkdir -p $L
gate() {
  ok=0
  while [ $ok -lt 3 ]; do
    if uv run python scripts/e3.py --stage probe >> $L/e3sl_probe.log 2>&1; then ok=$((ok+1)); echo "probe ok $ok/3 $(date -u +%FT%TZ)"; else ok=0; echo "probe fail $(date -u +%FT%TZ)"; fi
    [ $ok -lt 3 ] && sleep 300
  done
}
step() {  # $1 label, rest = e3sl.py args
  label=$1; shift
  echo "$label start $(date -u +%FT%TZ)"
  uv run python scripts/e3sl.py "$@" >> "$L/e3sl_$label.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "CHAIN_FAILED $label rc=$rc $(date -u +%FT%TZ)"; exit 1; fi
  echo "$label done $(date -u +%FT%TZ) $(uv run python scripts/e3sl.py --stage spend 2>/dev/null | head -c 60)"
}
step placebo --stage placebo
gate
step evals-anchors --stage evals --group anchors
step wait-shared --stage wait --for shared
step banks-O --stage banks --arm O
step wait-confirm --stage wait --for confirm
step banks-A --stage banks --arm A
step banks-G --stage banks --arm G
step banks-R --stage banks --arm R
step matched --stage matched
gate
step evals-matched --stage evals --group matched
gate
step evals-full --stage evals --group full
gate
step evals-cascade --stage evals --group cascade
step tables --stage tables
touch runs/E3SL_DONE
echo E3SL_DONE
