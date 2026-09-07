import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "eobs"))
from e1.lam_search import next_lambda, monotonicity_violations
from e1.operators.h_horizon import rules_code


def test_lambda_search_sequence():
    assert next_lambda([]) == 0.75
    assert next_lambda([(0.75, "NOEFFECT")]) == 0.875
    assert next_lambda([(0.75, "NOEFFECT"), (0.875, "ZERO")]) == 0.8125
    assert next_lambda([(0.75, "ZERO")]) == 0.625
    assert next_lambda([(0.75, "ZERO"), (0.625, "NOEFFECT")]) == 0.6875
    assert next_lambda([(0.75, "IN-BAND")]) is None
    assert next_lambda([(0.75, "NOEFFECT"), (0.875, "NOEFFECT"), (0.9375, "NOEFFECT"), (0.96875, "NOEFFECT")]) is None
    assert monotonicity_violations([(0.75, "ZERO"), (0.875, "NOEFFECT")]) == 1 and monotonicity_violations([(0.75, "NOEFFECT"), (0.875, "ZERO")]) == 0


def test_horizon_rules_terminates_at_m():
    from envharness.core.code_loader import load_rules_subclass
    from envharness.core.types import Action, EnvResponse, Observation
    cls = load_rules_subclass(rules_code(5))
    inst = cls(inner=None)
    class S: step_count = 5; won = False
    resp = EnvResponse(observation=Observation(text="x"), reward=0.0, terminated=False, truncated=False, info={"won": False})
    out = inst.modify_transition(Action(name="do", kwargs={"text": "look"}), resp, S())
    assert out.terminated and out.info["horizon_squeeze"] == 5 and out.reward == 0.0
    class S4: step_count = 4; won = False
    assert not inst.modify_transition(Action(name="do", kwargs={"text": "look"}), resp, S4()).terminated
    class SW: step_count = 5; won = True
    assert not inst.modify_transition(Action(name="do", kwargs={"text": "look"}), resp, SW()).terminated
