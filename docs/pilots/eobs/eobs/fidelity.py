"""Replay fidelity check (Phase-4 precondition): reset + replay a stored trajectory step by step and assert that
every step's stored raw_observation text equals the live observation verbatim. Also exercises the action-text path
(the stored action is the normalised command the bridge executed)."""

from __future__ import annotations

import json
from pathlib import Path

from eobs.replay import open_session


def check_trace(trace: dict) -> dict:
    seed = int(trace["rollout_seed"])
    steps = trace.get("steps") or []
    sess = open_session(None, seed)
    mism = []
    try:
        for i, st in enumerate(steps):
            text = (st.get("raw_action") or {}).get("kwargs", {}).get("text", "")
            r = sess.step_text(text)
            stored = ((st.get("raw_observation") or {}).get("text") or "")
            if r["obs"] != stored:
                mism.append({"step": i, "action": text, "live": r["obs"][:200], "stored": stored[:200]})
                break
            if r["terminated"] or r["truncated"]:
                break
        return {"episode_id": trace.get("episode_id"), "task_id": seed, "n_steps": len(steps), "identical": not mism,
                "success_stored": trace.get("success"), "success_live": sess.won, "mismatch": mism[:1]}
    finally:
        sess.close()


def main(run_dir: Path, n: int = 5) -> list[dict]:
    traces = [json.loads(l) for l in (Path(run_dir) / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    picked = [t for t in traces if t.get("steps")][:n]
    out = [check_trace(t) for t in picked]
    for r in out:
        print(json.dumps(r, ensure_ascii=False)[:400])
    return out


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
