"""ω(E′) — witness survival: share of the policy's successful P1 trajectories on a task that pass the verifier when replayed
verbatim in E′ (Setup/Rules stack built exactly as the runner does; eobs.replay). O-axis: ω = 1 by construction (still
computed, as a check); Chain: ω = 0 by construction (not replayed); CHS staged: n/a."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # scratch/e1pilot
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS))
from envharness.core.types import Action, Candidate  # noqa: E402
from eobs.replay import open_session, replay_actions  # noqa: E402


def p1_successes(task_id: int) -> list[list[str]]:
    tr = [json.loads(l) for l in (ROOT / "work" / "runs" / "e1_qwen_map" / "traces.jsonl").read_text().splitlines() if l.strip()]
    return [[s["raw_action"]["kwargs"].get("text", "") for s in t["steps"]] for t in tr if int(t["rollout_seed"]) == task_id and t.get("success") and not t.get("error")]


def omega(task_id: int, candidate: Candidate) -> tuple[float | None, int, int]:
    wits = p1_successes(task_id)
    if not wits:
        return None, 0, 0
    ok = 0
    for w in wits:
        s = open_session(candidate, task_id)
        try:
            ok += int(replay_actions(s, w).ok)
        finally:
            s.close()
    return ok / len(wits), ok, len(wits)


def candidate_from_row(row: dict) -> Candidate:
    from e1.operators import h_horizon, o_footer
    fam, dose = row["family"], row["dose"]
    if fam == "F_O":
        return Candidate(rules_code=o_footer.rules_code(int(row["task_id"]), float(dose)), in_env_actions=[])
    if fam == "F_H":
        return Candidate(rules_code=h_horizon.rules_code(int(dose)), in_env_actions=[])
    if fam in ("F_S0", "F_S0p"):
        return Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in row["in_env_actions"]])
    raise ValueError(fam)
