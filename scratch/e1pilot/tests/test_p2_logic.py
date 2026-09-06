import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from e1.controller import classify8, classify_after4, rollouts_needed, DOSES
from e1.operators.o_footer import fnv, masked, rules_code


def test_controller_rules():
    assert classify_after4(4) == "NOEFFECT" and classify_after4(0) == "ZERO" and classify_after4(2) is None
    assert rollouts_needed(4) == 4 and rollouts_needed(1) == 8
    assert classify8(3) == "IN-BAND" and classify8(4) == "IN-BAND" and classify8(5) == "IN-BAND"
    assert classify8(2) == "NEAR" and classify8(6) == "NEAR" and classify8(7) == "NOEFFECT" and classify8(8) == "NOEFFECT" and classify8(1) == "OVERSHOOT"
    assert DOSES[0] == ("F_S0", 1) and DOSES[-1] == ("F_O", 1.0)


def test_footer_hash_deterministic_and_dose():
    assert fnv("0:0") == fnv("0:0") and fnv("0:0") != fnv("0:1")
    assert all(masked(t, s, 1.0) for t in range(30) for s in range(50))
    assert not any(masked(t, s, 0.0) for t in range(30) for s in range(50))
    share = sum(masked(t, s, 0.5) for t in range(30) for s in range(50)) / 1500
    assert 0.4 < share < 0.6
    code = rules_code(7, 0.5)
    assert "class _Rules(Rules)" in code and "LAMBDA = 0.5" in code and "TASK_ID = 7" in code


def test_footer_rules_compile_and_mask():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "eobs"))
    from envharness.core.code_loader import load_rules_subclass
    from envharness.core.types import Observation
    cls = load_rules_subclass(rules_code(3, 1.0))
    inst = cls(inner=None)
    class S: step_count = 5
    obs = Observation(text="Task: x\n\nYou see a table.\n\nAdmissible commands: look, inventory", data={"admissible_commands": ["look", "inventory"], "goal_text": "x"})
    out = inst.filter_observation(obs, S())
    assert out.text == "Task: x\n\nYou see a table." and "admissible_commands" not in out.data and out.data["goal_text"] == "x"
    cls0 = load_rules_subclass(rules_code(3, 0.0))
    assert cls0(inner=None).filter_observation(obs, S()).text == obs.text


def test_goal_class_parsing():
    from e1.operators.s0_displace import _goal_class_from_text, _cls
    assert _goal_class_from_text("Your task is to: put two lettuce in fridge.") == "fridge"
    assert _goal_class_from_text("Your task is to: clean some egg and put it in microwave.") == "microwave"
    assert _goal_class_from_text("Your task is to: look at alarmclock under the desklamp.") == "desklamp"
    assert _goal_class_from_text("Your task is to: put a statue in sidetable.") == "sidetable"
    assert _cls("fridge 1") == "fridge" and _cls("countertop 12") == "countertop"
