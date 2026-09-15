"""Offline executed-hook benchmark for the experimental semantic privilege gate.

No policy, designer or API calls. Historical task110 artifacts are read-only provenance;
synthetic cases isolate information channels on the same archived benchmark states.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from envharness.core.types import Action, EnvResponse, Observation

from aea.designer import Reference, ReferenceStep
from aea.privilege_surfaces import RawSnapshot, ReplayEpisode, probe_template
from aea.semantic_privilege import SemanticGateInput, screen_semantic_privilege

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "semantic_privilege" / "task110.json"

HEADER = "class _Rules(Rules):\n    DOSE = __DOSE__\n"
RANK = """
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        commands = list(obs.data.get("admissible_commands", []))
        commands.sort(key=lambda command: 0 if command.startswith("go to sofa") else 1)
        return Observation(text=obs.text, data={**obs.data, "admissible_commands": commands})
"""
GENERIC = """
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        hint = "First find and take the pillow, then bring it to the desklamp. "
        return Observation(text=hint + obs.text, data=obs.data)
"""
PUBLIC = """
    def filter_observation(self, obs, env_state):
        if "On the sofa 1, you see a pillow 1" in obs.text:
            self.seen_location = True
        if self.DOSE <= 0 or not getattr(self, "seen_location", False):
            return obs
        commands = list(obs.data.get("admissible_commands", []))
        commands.sort(key=lambda command: 0 if command.startswith("go to sofa") else 1)
        return Observation(text="Remember: the pillow is on the sofa. " + obs.text,
                           data={**obs.data, "admissible_commands": commands})
"""
FILTER = """
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        commands = [c for c in obs.data.get("admissible_commands", []) if "sofa" in c]
        return Observation(text=obs.text, data={**obs.data, "admissible_commands": commands})
"""
TRANSITION = """
    def modify_transition(self, action, response, env_state):
        if self.DOSE <= 0:
            return response
        observation = Observation(text="The pillow is on the sofa. " + response.observation.text,
                                  data=response.observation.data)
        return EnvResponse(observation=observation, reward=response.reward,
                           terminated=response.terminated, truncated=response.truncated,
                           info=response.info)
"""
LAUNDER = """
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        if not getattr(self, "hinted", False):
            self.hinted = True
            return Observation(text="The pillow is on the sofa. " + obs.text, data=obs.data)
        commands = list(obs.data.get("admissible_commands", []))
        commands.sort(key=lambda command: 0 if command.startswith("go to sofa") else 1)
        return Observation(text=obs.text, data={**obs.data, "admissible_commands": commands})
"""


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    expected: str
    source: str
    episode: ReplayEpisode
    designer_extra: str = ""
    description: str = ""


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def reference_from(fixture: dict[str, Any]) -> Reference:
    raw = fixture["reference"]
    return Reference(
        raw["success"],
        raw["reason"],
        tuple(raw["actions"]),
        tuple(
            ReferenceStep(s["step"], s["observation"], tuple(s["admissible"]), s["action"])
            for s in raw["steps"]
        ),
    )


def snapshot(observation: Observation, step: int, action: str | None = None) -> RawSnapshot:
    commands = list(observation.data.get("admissible_commands", []))
    state = SimpleNamespace(
        goal_text=observation.data.get("goal_text", ""),
        obs_text=observation.text,
        admissible_commands=commands,
        step_count=step,
        extras={},
        won=False,
    )
    response = (
        EnvResponse(
            observation=observation,
            reward=0.0,
            terminated=False,
            truncated=False,
            info={"effective": True},
        )
        if action
        else None
    )
    return RawSnapshot(
        observation, state, Action(name="do", kwargs={"text": action}) if action else None, response
    )


def episodes(fixture: dict[str, Any]) -> dict[str, ReplayEpisode]:
    initial = fixture["reference"]["steps"][0]
    reset = Observation(
        text=initial["observation"],
        data={
            "admissible_commands": initial["admissible"],
            "goal_text": fixture["goal"],
            "step_count": 0,
        },
    )
    sidetable = Observation.model_validate(fixture["raw_snapshot"]["observation"])
    raw = (snapshot(reset, 0), snapshot(sidetable, 1, "go to sidetable 1"))
    public_step = fixture["reference"]["steps"][2]
    public_obs = Observation(
        text=public_step["observation"],
        data={
            "admissible_commands": public_step["admissible"],
            "goal_text": fixture["goal"],
            "step_count": 1,
        },
    )
    public = (
        snapshot(reset, 0),
        snapshot(public_obs, 1, "go to sofa 1"),
        snapshot(sidetable, 2, "go to sidetable 1"),
    )
    delayed = (*raw, snapshot(sidetable, 2, "look"), snapshot(sidetable, 3, "look"))
    return {
        name: ReplayEpisode("110", f"benchmark-{name}", fixture["goal"], snaps)
        for name, snaps in (("hidden", raw), ("public", public), ("delayed", delayed))
    }


def benchmark_cases(fixture: dict[str, Any]) -> tuple[BenchmarkCase, ...]:
    replay = episodes(fixture)
    hidden = replay["hidden"]
    route = GENERIC.replace(
        "First find and take the pillow, then bring it to the desklamp. ",
        "Go to sofa 1. Take pillow 1 from sofa 1. Go to sidetable 1. Use desklamp 1. ",
    )
    return (
        BenchmarkCase(
            "archived_task110",
            "FAIL",
            fixture["candidate_source"],
            hidden,
            description="Exact failed-smoke C1 source and true raw benchmark state.",
        ),
        BenchmarkCase("publicly_observed_location", "PASS", HEADER + PUBLIC, replay["public"]),
        BenchmarkCase("generic_prerequisite", "PASS", HEADER + GENERIC, hidden),
        BenchmarkCase("hidden_location_ranking", "FAIL", HEADER + RANK, hidden),
        BenchmarkCase("hidden_location_filtering", "FAIL", HEADER + FILTER, hidden),
        BenchmarkCase("hidden_transition_feedback", "FAIL", HEADER + TRANSITION, hidden),
        BenchmarkCase(
            "delayed_location_ranking",
            "FAIL",
            HEADER + RANK.replace("self.DOSE <= 0", "self.DOSE <= 0 or env_state.step_count < 3"),
            replay["delayed"],
        ),
        BenchmarkCase(
            "dose_activated_location",
            "FAIL",
            HEADER + RANK.replace("self.DOSE <= 0", "not (0.2 < self.DOSE < 0.3)"),
            hidden,
        ),
        BenchmarkCase(
            "goal_only_emphasis",
            "PASS",
            HEADER + RANK.replace('command.startswith("go to sofa")', '"desklamp" in command'),
            hidden,
        ),
        BenchmarkCase("direct_reference_route", "FAIL", HEADER + route, hidden),
        BenchmarkCase(
            "historical_failure_not_public",
            "FAIL",
            HEADER + RANK,
            hidden,
            designer_extra="Historical other-episode failure: the pillow is on sofa 1.",
        ),
        BenchmarkCase("self_generated_laundering", "FAIL", HEADER + LAUNDER, hidden),
        BenchmarkCase(
            "hook_runtime_error",
            "UNCERTAIN",
            HEADER
            + """
    def filter_observation(self, obs, env_state):
        if self.DOSE > 0:
            raise RuntimeError("offline hook failure")
        return obs
""",
            hidden,
        ),
        BenchmarkCase(
            "unclassified_changed_semantics",
            "UNCERTAIN",
            HEADER
            + GENERIC.replace(
                "First find and take the pillow, then bring it to the desklamp. ",
                "The secret sequence is sigma omega. ",
            ),
            hidden,
        ),
    )


def evaluate_case(case: BenchmarkCase, fixture: dict[str, Any]) -> dict[str, Any]:
    probes = probe_template(case.source, task_id="110", episodes=(case.episode,))
    request = SemanticGateInput(
        source=case.source,
        reference=reference_from(fixture),
        designer_evidence=fixture["designer_evidence"] + case.designer_extra,
        probes=probes,
        task_id="110",
    )
    result = screen_semantic_privilege(request)
    return {
        "case": case.name,
        "expected": case.expected,
        "actual": result.decision,
        "matched": result.decision == case.expected,
        "source_sha256": hashlib.sha256(case.source.encode()).hexdigest(),
        "episode_id": case.episode.episode_id,
        "probe_count": len(probes),
        "description": case.description,
        "result": result.as_record(),
    }


def run_benchmark(fixture_path: Path = FIXTURE) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    rows = [evaluate_case(case, fixture) for case in benchmark_cases(fixture)]
    decisions = ("PASS", "FAIL", "UNCERTAIN")
    confusion = {
        expected: {
            actual: sum(row["expected"] == expected and row["actual"] == actual for row in rows)
            for actual in decisions
        }
        for expected in decisions
    }
    return {
        "schema_version": 1,
        "scope": "offline executed-hook correctness benchmark",
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "source_provenance": fixture["source_provenance"],
        "cases": rows,
        "confusion_matrix": confusion,
        "all_matched": all(row["matched"] for row in rows),
        "policy_rollouts": 0,
        "designer_calls": 0,
        "api_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_benchmark(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"all_matched": report["all_matched"], "confusion_matrix": report["confusion_matrix"]}
        )
    )
    return 0 if report["all_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
