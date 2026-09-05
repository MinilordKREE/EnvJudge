"""Budget watchdog: every 60 s sum the ledger; at the soft gate (USD 80) kill EnvRigger/phase processes and log; hard cap 120."""

from __future__ import annotations

import subprocess
import sys
import time

from eobs.llm import ledger_totals
from eobs.settings import BUDGET_HARD_USD, BUDGET_SOFT_USD, EOBS_ROOT, RESULTS


def main() -> None:
    soft = float(sys.argv[1]) if len(sys.argv) > 1 else BUDGET_SOFT_USD
    while True:
        tot = ledger_totals(RESULTS / "ledger.jsonl")
        if tot["usd"] >= soft:
            msg = f"- {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} BUDGET GATE: ledger USD {tot['usd']:.2f} >= {soft}; killing rollout processes (soft gate → pause + interim report).\n"
            with open(EOBS_ROOT / "LOG.md", "a", encoding="utf-8") as fh:
                fh.write(msg)
            subprocess.run(["pkill", "-f", "eobs.run_rigger"]); subprocess.run(["pkill", "-f", "eobs.phase1"]); subprocess.run(["pkill", "-f", "eobs.phase3"])
            subprocess.run(["pkill", "-f", "episode_worker.py"])
            print(msg, flush=True)
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
