"""F_O — admissible-commands footer masking at dose λ ∈ {0.5, 1.0}.

The released `_Rules` template removes the footer at step s iff hash(task_id, s) mod 100 < 100·λ. Deterministic (no RNG):
the hash is a fixed FNV-1a over f"{task_id}:{s}". `env_state.step_count` is the step index (0 at reset; audited in LOG).
Nothing else in the observation changes; obs.data (incl. admissible_commands) is passed through untouched, so the policy's
THINK_ACTION reminder still lists admissibles from obs.data unless the runner's PolicyAgent is also masked -- see NOTE.

NOTE: envharness's PolicyAgent (think_action) appends "Admissible actions: [...]" from obs.data["admissible_commands"].
To mask the footer for the policy, the O hook must therefore also drop that key from obs.data at masked steps; the bridge
keeps its own copy in env_state, so the env is unaffected. This is what the released designer's O-axis candidates did too.
"""

from __future__ import annotations

FOOTER = "\n\nAdmissible commands: "

TEMPLATE = '''
def _fnv(s):
    h = 2166136261
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) % 4294967296
    return h


class _Rules(Rules):
    LAMBDA = {lam}
    TASK_ID = {task_id}

    def _masked(self, env_state):
        s = int(getattr(env_state, "step_count", 0) or 0)
        return (_fnv(f"{{self.TASK_ID}}:{{s}}") % 100) < int(round(100 * self.LAMBDA))

    def filter_observation(self, obs, env_state):
        if not self._masked(env_state):
            return obs
        text = obs.text
        i = text.find("\\n\\nAdmissible commands: ")
        if i >= 0:
            text = text[:i]
        data = dict(obs.data or {{}})
        data.pop("admissible_commands", None)
        return Observation(text=text, data=data)
'''


def rules_code(task_id: int, lam: float) -> str:
    return TEMPLATE.format(lam=float(lam), task_id=int(task_id)).strip() + "\n"


def fnv(s: str) -> int:
    h = 2166136261
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) % 4294967296
    return h


def masked(task_id: int, step: int, lam: float) -> bool:
    return (fnv(f"{task_id}:{step}") % 100) < int(round(100 * lam))
