"""E1-pilot watchdog: every 30 s scan results/e1pilot/ledger.jsonl. Kill the pilot's rollout processes and log if
(a) cumulative USD >= soft gate (50), (b) any row's provider is not 'Alibaba' for a qwen model, or (c) any row's upstream
usage.cost deviates from the verified 0.117/0.455 per M by more than 1e-7 USD absolute + 0.5 % relative."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LED = ROOT / "results" / "e1pilot" / "ledger.jsonl"
SOFT = 100.0
PHASE_CAPS = {"p1_map": 28.0, "p2_dose": 30.0, "p3_skills": 40.0, "p4": 70.0}   # owner budget update (P1-gate decision, then 2026-09-07 update)
IN, OUT = 0.117e-6, 0.455e-6


def scan() -> tuple[float, str | None]:
    usd = 0.0
    by_phase: dict[str, float] = {}
    if not LED.exists():
        return 0.0, None
    for line in LED.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        usd += float(r.get("usd") or 0.0)
        by_phase[r.get("phase", "")] = by_phase.get(r.get("phase", ""), 0.0) + float(r.get("usd") or 0.0)
        for ph, cap in PHASE_CAPS.items():
            if by_phase.get(ph, 0.0) >= cap:
                return usd, f"phase cap: {ph} USD {by_phase[ph]:.2f} >= {cap}"
        if not r.get("ok") or "qwen" not in str(r.get("model", "")):
            continue
        if r.get("provider") != "Alibaba":
            return usd, f"provider mismatch: {r.get('provider')!r} in row ts={r.get('ts')} run={r.get('run_id')}"
        uc = r.get("upstream_cost")
        if uc is not None:
            exp = r.get("prompt_tokens", 0) * IN + r.get("completion_tokens", 0) * OUT
            if abs(float(uc) - exp) > 1e-7 + 0.005 * exp:
                return usd, f"cost mismatch: usage.cost={uc} expected={exp:.8f} (tokens {r.get('prompt_tokens')}/{r.get('completion_tokens')}) ts={r.get('ts')}"
    return usd, None


def main() -> None:
    while True:
        usd, problem = scan()
        if problem or usd >= SOFT:
            msg = f"- {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} WATCHDOG ABORT: {problem or f'soft gate: USD {usd:.2f} >= {SOFT}'}; killing e1 rollout processes.\n"
            (ROOT / "LOG.md").open("a", encoding="utf-8").write(msg)
            for pat in ("e1/regime_map.py", "e1/p2_run.py", "episode_worker.py"):
                subprocess.run(["pkill", "-f", pat])
            print(msg, flush=True)
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
