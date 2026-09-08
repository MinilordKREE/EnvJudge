#!/bin/bash
# D1 chain: wait for the corpus success line, then released banks over the merged 100-task traces,
# then orig_100 / R_100 evals on 3 seeds in parallel, then the report.
cd /home/kree/work/EnvJudge
export ALFWORLD_DATA=$HOME/eh_alfworld_data
until grep -q '"stage": "corpus"' runs/e0d1_corpus.log; do
  if ! pgrep -f "run-id e0d1-20260908 --task-ids" > /dev/null; then echo "CORPUS_PROCESS_GONE"; exit 1; fi
  sleep 30
done
uv run python scripts/e0.py --stage banks_released --run-id e0d1-20260908 --merge-traces e0-20260907 || { echo BANKS_FAILED; exit 1; }
E="uv run python scripts/e0.py --stage eval --run-id e0d1-20260908 --concurrency 8 --tag released100"
for s in 0 1000 2000; do
  $E --seeds $s --conditions "orig_100=banks_released/orig_full.jsonl,R_100=banks_released/ours_full.jsonl" > runs/e0d1_eval_seed$s.log 2>&1 &
done
wait
uv run python scripts/e0.py --stage report --run-id e0d1-20260908 --n-from e0-20260907
echo D1_CHAIN_DONE
