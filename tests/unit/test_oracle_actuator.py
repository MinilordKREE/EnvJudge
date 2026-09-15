"""Phase 3.5a oracle actuator ceiling (docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md): the
frozen dossier (seven families, one per task), identity at d = 0, legality at d = 1, one
mechanism with a coverage dose (support counts monotone in d on scripted episodes), the privilege
boundary (no numbered instance constant, no reference action, no Setup prefix), the exact
reference provenance of the provider path, and the phase-3.4 controller reused unchanged
(provider injected: d = 1 first, same acceptance, same cap including the replayed estimate,
no designer record, corpus source ``oracle``); production controllers never see a provider."""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from envharness.core.code_loader import load_rules_subclass
from envharness.core.types import Action, Blocked, EnvResponse, Observation

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.designer import Reference, ReferenceStep, identity_at_zero
from aea.families import validate_rules_template
from aea.io import read_corpus
from tests.unit.test_assistive_rules import DoseSubstrate

ROOT = Path(__file__).resolve().parents[2]
AR = AEAConfig(method_version="llm_v1_assistive_rules")


def _load(name: str) -> Any:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oa = _load("oracle_actuators")
TASKS = ("85", "86", "92", "97", "99", "107", "109")
T, F = True, False


# ----------------------------------------------------------------------------- fake world
class _State:
    def __init__(self) -> None:
        self.extras: dict[str, Any] = {}


class _Inner:
    def __init__(self) -> None:
        self.state = _State()
        self.obs = _obs("You see a room.", ["look"])

    def get_env_state(self) -> _State:
        return self.state

    def observe(self) -> Observation:
        return self.obs

    def step(self, action: Action) -> EnvResponse:
        return EnvResponse(
            observation=self.obs, reward=0.0, terminated=False, truncated=False, info={}
        )


def _obs(msg: str, cmds: list[str]) -> Observation:
    return Observation(
        text="Task: x\n\n" + msg + "\n\nAdmissible commands: " + ", ".join(cmds),
        data={"admissible_commands": list(cmds), "goal_text": "x"},
    )


def _inst(task: str, d: float) -> Any:
    fam = oa.families()[task]
    code = fam.template.replace("__DOSE__", repr(d)).replace("__TASK_ID__", repr(task))
    return load_rules_subclass(code)(inner=_Inner())


WELCOME = "-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room."


# ----------------------------------------------------------------------------- the dossier
def test_dossier_frozen_one_family_per_task_and_matches_registry() -> None:
    reg = json.loads((oa.DOSSIER / "REGISTRY.json").read_text())
    assert reg["tasks"] == list(TASKS) and [s.task for s in oa.SPECS] == list(TASKS)
    assert len({s.task for s in oa.SPECS}) == 7  # exactly one family per task
    for spec in oa.SPECS:
        on_disk = oa.template_path(spec.task).read_text(encoding="utf-8")
        assert on_disk == oa.render(spec), f"family {spec.task} drifted from the registry"
        assert reg["template_sha256_16"][spec.task] == oa.sha(on_disk)
        assert oa.record_path(spec.task).exists()
    frozen = oa.frozen_families()
    assert set(frozen) == set(TASKS)
    for fam in frozen.values():
        assert fam.source == "oracle" and fam.direction == "easier_with_d"


@pytest.mark.parametrize("task", TASKS)
def test_identity_at_zero_and_legal_at_one(task: str) -> None:
    fam = oa.frozen_families()[task]
    assert identity_at_zero(fam.template, task_id=task) == []
    rep = validate_rules_template(fam.template, task_id=task)
    assert rep.ok, rep.reasons


@pytest.mark.parametrize("task", TASKS)
def test_privilege_boundary_no_instance_constant_no_reference_action(task: str) -> None:
    code = oa.frozen_families()[task].template
    # no numbered object / receptacle instance in the code (only type words), no inner step,
    # no verifier / reward / termination edit, no Setup replay
    literals = re.findall(r"[\"']([^\"']*)[\"']", code)
    for lit in literals:
        for m in re.finditer(r"\b([a-z]+) \d+\b", lit):
            # prose words of the docstrings ("dose 0") are not ALFWorld object instances
            assert m.group(1) in ("dose", "step", "steps", "d"), (
                f"instance constant in {task}: {m.group(0)!r}"
            )
    for pat in (
        r"\.step\(",
        r"\bwon\s*=",
        r"success\W*[=:]\s*True",
        r"terminated\s*=\s*True",
        r"\breward\s*=",
        "in_env_actions",
    ):
        assert not re.search(pat, code), f"{pat} in family {task}"
    spec = oa.SPEC_BY_TASK[task]
    assert spec.obj in spec.goal  # the object type is a goal word


# ------------------------------------------------------------ one mechanism, coverage dose
def _s_episode(task: str, d: float) -> list[int]:
    """Class S on a scripted search: number of `go to` commands removed per observation."""
    r = _inst(task, d)
    st = r.inner.state
    obj = oa.SPEC_BY_TASK[task].obj
    seq = [
        (WELCOME, ["go to fridge 1", "go to cabinet 1", "go to cabinet 2", "go to sinkbasin 1"]),
        (
            "You arrive at fridge 1. The fridge 1 is closed.",
            [
                "open fridge 1",
                "go to cabinet 1",
                "go to cabinet 2",
                "go to sinkbasin 1",
                "go to fridge 1",
            ],
        ),
        (
            "You open the fridge 1. The fridge 1 is open. In it, you see a bowl 1, a mug 1.",
            [
                "close fridge 1",
                "go to cabinet 1",
                "go to cabinet 2",
                "go to sinkbasin 1",
                "go to fridge 1",
            ],
        ),
        (
            "You arrive at cabinet 1. On the cabinet 1, you see nothing.",
            ["go to cabinet 2", "go to sinkbasin 1", "go to fridge 1", "go to cabinet 1"],
        ),
        (
            "You arrive at cabinet 2. On the cabinet 2, you see a plate 1.",
            ["go to cabinet 2", "go to sinkbasin 1", "go to fridge 1", "go to cabinet 1"],
        ),
        (
            f"You arrive at sinkbasin 1. On the sinkbasin 1, you see a {obj} 1.",
            [
                f"take {obj} 1 from sinkbasin 1",
                "go to fridge 1",
                "go to cabinet 1",
                "go to cabinet 2",
            ],
        ),
        (
            f"You pick up the {obj} 1 from the sinkbasin 1.",
            ["go to fridge 1", "go to cabinet 1", "go to cabinet 2", "go to sinkbasin 1"],
        ),
    ]
    removed = []
    for msg, cmds in seq:
        out = r.filter_observation(_obs(msg, cmds), st)
        removed.append(len(cmds) - len(out.data["admissible_commands"]))
        assert out.data["admissible_commands"] == [
            c for c in cmds if c in out.data["admissible_commands"]
        ]
    assert removed[-1] == 0  # everything returns once the goal object is held
    return removed


def _p_episode(task: str, d: float) -> tuple[int, bool]:
    """Class P: number of premature attempts blocked out of 8, and pass-through afterwards."""
    r = _inst(task, d)
    st = r.inner.state
    spec = oa.SPEC_BY_TASK[task]
    act = {"held": "use desklamp 1", "cleaned": f"move {spec.obj} 1 to garbagecan 1"}[spec.precond]
    r.filter_observation(_obs(WELCOME, ["look"]), st)
    blocked = 0
    for _ in range(8):
        out = r.filter_action(Action(name="do", kwargs={"text": act}), st)
        blocked += isinstance(out, Blocked)
        if isinstance(out, Blocked):
            assert out.reason == spec.reason
    r.filter_observation(_obs(f"You pick up the {spec.obj} 1 from the fridge 1.", ["look"]), st)
    if spec.precond == "cleaned":
        r.filter_observation(
            _obs(f"You clean the {spec.obj} 1 using the sinkbasin 1.", ["look"]), st
        )
    passes = isinstance(r.filter_action(Action(name="do", kwargs={"text": act}), st), Action)
    return blocked, passes


def _g_episode(task: str, d: float) -> int:
    r = _inst(task, d)
    st = r.inner.state
    n = 0
    for i in range(8):
        out = r.filter_observation(
            _obs(WELCOME if i == 0 else f"You arrive at cabinet {i}.", ["look"]), st
        )
        n += "Goal steps:" in out.text
        assert out.data["admissible_commands"] == ["look"]
    return n


@pytest.mark.parametrize("task", TASKS)
def test_same_mechanism_support_monotone_in_dose(task: str) -> None:
    spec = oa.SPEC_BY_TASK[task]
    doses = (0.0, 0.25, 0.5, 0.75, 1.0)
    if spec.cls == "S":
        totals = [sum(_s_episode(task, d)) for d in doses]
    elif spec.cls == "P":
        res = [_p_episode(task, d) for d in doses]
        assert all(p for _, p in res)  # the gate opens once the precondition holds
        totals = [b for b, _ in res]
    else:
        totals = [_g_episode(task, d) for d in doses]
    assert totals[0] == 0 and totals[-1] > 0
    assert all(a <= b for a, b in itertools.pairwise(totals)), totals


def test_class_s_never_prunes_the_receptacle_holding_the_goal_object() -> None:
    removed = _s_episode("85", 1.0)
    assert removed[5] == 3  # fridge, cabinet 1, cabinet 2 pruned; the tomato's surface stays
    r = _inst("85", 1.0)
    st = r.inner.state
    r.filter_observation(_obs(WELCOME, ["go to diningtable 1"]), st)
    out = r.filter_observation(
        _obs(
            "You arrive at diningtable 1. On the diningtable 1, you see a tomato 1.",
            ["take tomato 1 from diningtable 1", "go to diningtable 1"],
        ),
        st,
    )
    assert "go to diningtable 1" in out.data["admissible_commands"]


# ------------------------------------------------------------ provider + controller
REF = Reference(
    True,
    "pass",
    ("go to a", "take x 1 from a", "go to b"),
    (
        ReferenceStep(
            1, "You arrive at a. On the a, you see a x 1.", ("take x 1 from a",), "take x 1 from a"
        ),
        ReferenceStep(2, "You pick up the x 1 from the a.", ("go to b",), "go to b"),
    ),
)


def test_provider_returns_the_frozen_family_validated_and_no_setup_prefix() -> None:
    from tests.unit.test_llm_v1 import _trace

    fails = [_trace(False, n=3)]
    design = oa.provider(TaskRef("92", 92), fails, REF, "look at cellphone under the desklamp")
    assert len(design.families) == 1 and design.rejected == []
    fam = design.families[0]
    assert fam.name == "precondition_gating" and fam.source == "oracle"
    from aea.families import FamilyContext

    c = fam.make(1.0, FamilyContext(task_id="92"))
    assert c is not None and c.in_env_actions == [] and "DOSE = 1.0" in c.rules_code
    assert design.arguments["code_sha256"] == oa.sha(fam.template)
    missing = oa.provider(TaskRef("87", 87), fails, REF, "x")
    assert missing.families == [] and missing.rejected[0].startswith("NO_ORACLE_FAMILY")


def test_controller_reuses_the_assist_path_with_the_provider(tmp_path: Path) -> None:
    """The provider path: d = 1 first (4 -> 8), in-band accept, corpus source oracle, no
    designer record, reference provenance = the injected reference, cap 30 incl. estimate."""
    sub = DoseSubstrate({("precondition_gating", 1.0): [T, F, T, F, T, F, T, F]}, [])
    seen: list[tuple[str, Reference, str]] = []

    def provider(task: TaskRef, failures: Any, reference: Reference, goal: str) -> Any:
        seen.append((task.task_id, reference, goal))
        return oa.provider(task, failures, reference, goal)

    ctrl = Controller(
        AR,
        sub,
        tmp_path,
        "oracle",
        arm="O",
        use_proposer=True,
        reference=lambda task: REF,
        assist_provider=provider,
    )
    out = ctrl.run([TaskRef("92", 92)], concurrency=1)[0]
    assert out.outcome == "accepted" and out.detail["d"] == 1.0 and out.detail["doses"] == [1.0]
    assert seen and seen[0][1] is REF
    assert not (tmp_path / "designer_calls.jsonl").exists()
    rows = [
        json.loads(line) for line in (tmp_path / "oracle_families.jsonl").read_text().splitlines()
    ]
    assert rows[0]["mode"] == "oracle" and rows[0]["families"][0]["name"] == "precondition_gating"
    entries = read_corpus(tmp_path / "corpus.jsonl")
    assert entries[-1].aea.kind == "knob" and entries[-1].aea.source == "oracle"
    assert entries[-1].in_env_actions == []
    kinds = [
        json.loads(line)["kind"] for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert "oracle_actuator" in kinds and "llm_assist_proposals" not in kinds
    assert "stage_candidates" not in kinds and "families" not in kinds
    assert out.n_search <= AR.cap == 30


def test_controller_without_provider_never_touches_the_oracle_path(tmp_path: Path) -> None:
    from tests.unit.test_assistive_rules import HINT, _reply

    sub = DoseSubstrate({("hint_a", 1.0): [T, F, T, F, T, F, T, F]}, _reply(HINT))
    ctrl = Controller(
        AR, sub, tmp_path, "llm", arm="B", use_proposer=True, reference=lambda task: REF
    )
    assert ctrl.assist_provider is None
    out = ctrl.run([TaskRef("92", 92)], concurrency=1)[0]
    assert out.outcome == "accepted"
    assert not (tmp_path / "oracle_families.jsonl").exists()
    assert read_corpus(tmp_path / "corpus.jsonl")[-1].aea.source == "llm"


def test_provider_rejects_a_privileged_family_instead_of_repairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_llm_v1 import _trace

    original = oa.frozen_families()["92"]
    bad = original.template.replace("REASON = ", "REASON = 'go to armchair 1 ' + ")
    tainted = oa.AssistFamily(name=original.name, axis=original.axis, template=bad, source="oracle")
    monkeypatch.setattr(oa, "frozen_families", lambda: {"92": tainted})
    ref = Reference(True, "pass", ("go to armchair 1", "take cellphone 1 from armchair 1"), ())
    design = oa.provider(
        TaskRef("92", 92), [_trace(False, n=2)], ref, "look at cellphone under the desklamp"
    )
    assert design.families == [] and "reference action embedded" in design.rejected[0]
