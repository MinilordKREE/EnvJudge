from __future__ import annotations

from aea.displacement import (
    TaskInfo,
    build,
    destination_order,
    discover,
    goal_class_from_text,
    n_targets_for,
    receptacle_class,
    setup_builder,
    synthesize,
    validate,
)
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]


def test_goal_class_cases_from_the_pilot() -> None:
    assert goal_class_from_text("Your task is to: put two lettuce in fridge.") == "fridge"
    assert (
        goal_class_from_text("Your task is to: clean some egg and put it in microwave.")
        == "microwave"
    )
    assert (
        goal_class_from_text("Your task is to: look at alarmclock under the desklamp.")
        == "desklamp"
    )
    assert goal_class_from_text("Your task is to: put a statue in sidetable.") == "sidetable"
    assert (
        receptacle_class("cabinet 10") == "cabinet" and n_targets_for("put two mug in fridge") == 2
    )


def test_synthesize_excludes_source_and_goal_class_and_orders_deterministically() -> None:
    info = TaskInfo(
        task_id="7",
        targets=[("statue 3", "shelf 2")],
        receptacles=["shelf 1", "shelf 2", "sidetable 1", "drawer 1", "cabinet 1"],
        openable={"drawer 1": True, "cabinet 1": True},
        goal_recep_class="sidetable",
    )
    k1 = synthesize(info, 1)
    dests = [next(a for a in acts if a.startswith("move ")).split(" to ")[1] for acts in k1]
    assert set(dests) == {"shelf 1"} and all(acts[-1] == "look" for acts in k1)
    assert k1[0][:5] == [
        "go to shelf 2",
        "take statue 3 from shelf 2",
        "go to shelf 1",
        "move statue 3 to shelf 1",
        "look",
    ]
    k2 = synthesize(info, 2)
    assert {next(a for a in acts if a.startswith("move ")).split(" to ")[1] for acts in k2} == {
        "drawer 1",
        "cabinet 1",
    }
    assert "open drawer 1" in k2[0] or "open cabinet 1" in k2[0]
    k3 = synthesize(info, 3)
    assert any(a.startswith("close ") for a in k3[0]) and len(k3[0]) > len(k2[0])
    assert destination_order(["a", "b", "c"], "7", 1) == destination_order(["a", "b", "c"], "7", 1)
    assert synthesize(TaskInfo(task_id="1", targets=[("x", "a")], receptacles=["a"]), 1) == []


def test_discover_validate_and_build_on_the_fake_world() -> None:
    open_fn = make_open(PLAN)
    info = discover(open_fn)
    assert info is not None and info.targets == [("x", "a")] and info.goal_recep_class == "b"
    assert "c" in info.receptacles and info.openable.get("c") is False
    ok, why = validate(open_fn, ["go to a", "take x from a", "go to c", "move x to c", "look"])
    assert not ok and "not admissible" in why  # the fake world has no move to c
    ok, why = validate(open_fn, ["go to a", "look"])
    assert ok and why == "ok"
    actions, status = build(open_fn, info, 1)
    assert actions is None and status.startswith(
        "infeasible"
    )  # no valid open destination in the fake
    builder = setup_builder(open_fn)
    assert builder(1 / 3) is None and builder(1.0) is None
