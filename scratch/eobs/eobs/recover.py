"""Recoverability along a failed trajectory's own prefixes (LLM-free).

For a failed base-env trajectory with actions a_1..a_T: for t = 0..min(T, cap), s_t = reset ∘ a_1..a_t and
C(s_t) = 1 iff the closed-loop expert from s_t reaches success. Each prefix is a fresh session
(reset + replay), so the stateful handcoded expert observes exactly the prefix before it takes over.
"""

from __future__ import annotations

from eobs.replay import EXPERT_MAX_STEPS, RECOVER_MODE, open_session, replay_actions, run_expert


def c_at(seed: int, prefix: list[str], max_steps: int = EXPERT_MAX_STEPS) -> tuple[int, str]:
    sess = open_session(None, seed)
    try:
        if prefix:
            rp = replay_actions(sess, prefix)
            if sess.won:
                return 1, "already_won"
            if sess.done:
                return 0, "done_before_expert"
            if rp.reason == "env_error":
                return 0, "env_error"
        res = run_expert(sess, max_steps=max_steps)
        return (1 if res.ok else 0), res.reason
    finally:
        sess.close()


def recoverability(trajectory_id: str, task_id: int, actions: list[str], cap: int = 50) -> dict:
    T = len(actions)
    n = min(T, cap)
    c_seq: list[int] = []
    reasons: list[str] = []
    for t in range(n + 1):
        c, reason = c_at(task_id, actions[:t])
        c_seq.append(c)
        reasons.append(reason)
    ones = [t for t, c in enumerate(c_seq) if c == 1]
    zeros = [t for t, c in enumerate(c_seq) if c == 0]
    L = max(ones) if ones else -1
    first_zero = min(zeros) if zeros else None
    monotone = 1 if (first_zero is None or not any(t > first_zero for t in ones)) else 0
    return {"trajectory_id": trajectory_id, "task_id": task_id, "T": T, "T_eval": n, "C_seq": c_seq, "L": L,
            "first_zero": first_zero, "monotone": monotone, "expert_errors": sum(r == "expert_error" for r in reasons),
            "reasons": reasons, "recover_mode": RECOVER_MODE}


def summarize(rec: dict) -> dict:
    T = max(rec["T_eval"], 1)
    return {"L_over_T": (rec["L"] / T) if rec["L"] >= 0 else 0.0, "L_ge_2": rec["L"] >= 2, "non_monotone": rec["monotone"] == 0}
