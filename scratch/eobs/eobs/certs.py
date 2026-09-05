"""Certificate bookkeeping: R_old / R_exp / R_hint -> certified / unresolved (pure data; no env calls)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ReplayResult:
    ok: bool
    reason: str = ""            # "pass" | "verifier_fail" | "expert_error" | "blocked" | "env_error" | "not_run"
    step: int | None = None     # failing step index (0-based) when known
    n_steps: int = 0
    actions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HintResult:
    attempts: int = 0
    ok: bool = False
    passing_actions: list | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def certified(r_old: ReplayResult | None, r_exp: ReplayResult | None, r_hint: HintResult | None) -> bool:
    return bool((r_old and r_old.ok) or (r_exp and r_exp.ok) or (r_hint and r_hint.ok))


def certificate_row(candidate_id: str, axis_label: str, r_old, r_exp, r_hint, witness_sha: str | None) -> dict:
    cert = certified(r_old, r_exp, r_hint)
    return {
        "candidate_id": candidate_id,
        "axis": axis_label,
        "R_old": r_old.to_dict() if r_old else None,
        "R_exp": r_exp.to_dict() if r_exp else None,
        "R_hint": r_hint.to_dict() if r_hint else None,
        "certified": cert,
        "unresolved": not cert,
        "witness_sha": witness_sha,
    }


def needs_hint(sr_c: float, r_old: ReplayResult | None) -> bool:
    """R_hint is run only for SR_c == 0 or R_old == 0 (pre-registered rule)."""
    return sr_c == 0.0 or (r_old is not None and not r_old.ok)
