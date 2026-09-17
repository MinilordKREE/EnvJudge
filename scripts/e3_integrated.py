"""Complete AEA integration and a separate E3 arm; raw artifacts remain under runs/.

Commands: freeze (offline), run, audit (offline), report (offline). No implicit restart
of a started task or confirmation, and no changes to historical experiment launchers.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import fcntl
import gzip
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import yaml
from envharness.core.types import Candidate, Trace
from scripts import e3

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.io import append_jsonl, atomic_write_json, read_json, read_jsonl
from aea.errors import ConfigError, InfraError
from aea.integrated_artifacts import build_task_artifact, method_state_sha256, public_task_metadata
from aea.io import read_corpus
from aea.llm.attribution import attributed
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.physical_audit import AuditedTransport, physical_summary
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatMessage, ChatRequest, ChatResponse
from aea.privilege_judge import JudgeConfig, JudgeRecord, PrivilegeJudgeInput, canonical_json
from aea.privilege_witness import WitnessCheckingPrivilegeJudge, validate_witness_record
from aea.runner import merge_ledgers
from aea.settings import load_settings
from aea.substrate import AeaSubstrate

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/e3-integrated/private"
EXP = ROOT / "experiments/alfworld_e3"
PREREG = EXP / "PREREG_INTEGRATED_AEA.md"
FROZEN = EXP / "frozen/integrated_aea.json"
OLD = EXP / "results/e3_layer1_data.json"
PROTOCOL = "e3-integrated-aea-v1"
ARM = "AEA-integrated"
TASKS = tuple(range(30))
TASK_CONCURRENCY = 4
ROLLOUT_CONCURRENCY = 4
STOP = threading.Event()
PRINT_LOCK = threading.Lock()
EPISODE_LOCK = threading.Lock()
SEEN_EPISODES: set[str] = set()


def digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value).encode()
    return hashlib.sha256(data).hexdigest()


def rows(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path) if path.exists() else []


def emit(**payload: Any) -> None:
    with PRINT_LOCK:
        print(json.dumps({"ts": time.time(), **payload}, sort_keys=True), flush=True)


def config() -> AEAConfig:
    return AEAConfig(method_version="llm_v2_integrated")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_hashes() -> dict[str, str]:
    paths = set(ROOT.glob("src/aea/**/*.py"))
    paths.update(ROOT.glob("third_party/envharness/envharness/**/*.py"))
    paths.update(ROOT.glob("tests/unit/test_integrated*.py"))
    paths.update(ROOT.glob("tests/unit/test_e3_integrated*.py"))
    paths.add(ROOT / "tests/unit/test_physical_audit.py")
    paths.update(ROOT.glob("third_party/envharness/envharness/third_party/alfworld/*.yaml"))
    paths.update(
        ROOT / p
        for p in (
            "scripts/e3_integrated.py",
            "scripts/make_tables_e3_integrated.py",
            "scripts/e3.py",
            "configs/corpus_aea.yaml",
            "configs/alfworld_config_100.yaml",
            "configs/pricing.yaml",
            "configs/privilege_judge_pricing.yaml",
            "uv.lock",
            "pyproject.toml",
            "docs/design/AEA_INTEGRATED.md",
            "experiments/alfworld_e3/PREREG_INTEGRATED_AEA.md",
            "experiments/alfworld_e3/results/e3_layer1_data.json",
        )
    )
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def runtime_fingerprint() -> dict[str, Any]:
    """Enumerate the frozen seed mapping without creating a simulator or policy episode."""
    data = Path(os.environ.get("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data")))
    os.environ.setdefault("ALFWORLD_DATA", str(data))
    path = ROOT / "third_party/envharness/envharness/third_party/alfworld/base_config.yaml"
    cfg = yaml.safe_load(path.read_text())
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        module = importlib.import_module("alfworld.agents.environment.alfred_tw_env")
        games = list(module.AlfredTWEnv(cfg, train_eval="train").game_files)
    selected = []
    for task in TASKS:
        choices = list(games)
        np.random.RandomState(task).shuffle(choices)
        game = Path(choices[0])
        selected.append(
            {
                "task_id": task,
                "path_sha256": digest(str(game)),
                "file_sha256": digest(game.read_bytes()),
            }
        )
    modules = (
        "alfworld.agents.environment.alfred_tw_env",
        "textworld.gym.envs.textworld_batch",
        "textworld.gym.envs.utils",
    )
    return {
        "games": len(games),
        "ordered_game_paths_sha256": digest(games),
        "tasks": selected,
        "logic": {
            name: digest((data / "logic" / name).read_bytes())
            for name in ("alfred.pddl", "alfred.twl2")
        },
        "selection_runtime": {
            name: digest(Path(str(importlib.import_module(name).__file__)).read_bytes())
            for name in modules
        },
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("alfworld", "textworld", "numpy", "openai", "envharness")
        },
    }


def freeze() -> None:
    if BASE.exists() and any(BASE.rglob("started.json")):
        raise ConfigError("Cannot refreeze after execution started")
    atomic_write_json(
        FROZEN,
        {
            "protocol": PROTOCOL,
            "method": config().model_dump(mode="json"),
            "policy": e3.policy_qwen().model_dump(mode="json"),
            "designer": e3.designer_deepseek().model_dump(mode="json"),
            "judge": JudgeConfig().model_dump(mode="json"),
            "source_hashes": source_hashes(),
            "runtime_fingerprint": runtime_fingerprint(),
            "tasks": list(TASKS),
            "concurrency": {"tasks": TASK_CONCURRENCY, "rollouts": ROLLOUT_CONCURRENCY},
            "usd_cap": None,
            "baseline_cap": 16,
            "adaptation_cap": 30,
            "confirmation_k": 16,
            "judge_phase_a_ready": False,
        },
    )
    emit(stage="frozen_offline", files=len(source_hashes()), sha256=digest(FROZEN.read_bytes()))


def ensure_frozen(*, paid: bool = False) -> dict[str, Any]:
    manifest = cast(dict[str, Any], read_json(FROZEN))
    if manifest["protocol"] != PROTOCOL or manifest["source_hashes"] != source_hashes():
        raise ConfigError("Frozen source/input hash mismatch")
    if manifest["runtime_fingerprint"] != runtime_fingerprint():
        raise ConfigError("Frozen dataset mapping or runtime dependency mismatch")
    if paid and git("status", "--porcelain", "--untracked-files=no"):
        raise ConfigError("Paid execution requires the committed implementation freeze")
    if manifest["method"] != config().model_dump(mode="json"):
        raise ConfigError("Method config differs from preregistered integration")
    return manifest


def logged_complete(
    client: OpenAICompatibleClient, directory: Path
) -> Callable[[ChatRequest], ChatResponse]:
    def complete(request: ChatRequest) -> ChatResponse:
        if STOP.is_set():
            raise InfraError("Experiment stopped after another task failed", kind="experiment_stop")
        append_jsonl(directory / "requests.jsonl", request.model_dump(mode="json"))
        with attributed(request.attribution, request.seed):
            response = client.complete(request)
        append_jsonl(directory / "responses.jsonl", response.model_dump(mode="json"))
        return response

    return complete


class AuditedSubstrate(AeaSubstrate):
    """Preserve runner behavior and add private request/physical accounting."""

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None:
        if self._designer is None:
            return None
        return logged_complete(self._designer, self.run_dir / "raw/designer")

    def privilege_judge(self, attribution: Attribution) -> WitnessCheckingPrivilegeJudge:
        judge_cfg = JudgeConfig()
        if self._judge_client is None:
            llm = judge_cfg.llm_config()
            transport = make_openai_transport(
                api_key=load_settings(ROOT / ".env").require(llm.api_key_env.lower()),
                base_url=llm.base_url,
                timeout_s=llm.timeout_s,
            )
            pricing = ROOT / "configs/privilege_judge_pricing.yaml"
            self._judge_client = OpenAICompatibleClient(
                config=llm,
                transport=AuditedTransport(
                    transport,
                    self.run_dir / "physical",
                    config=llm,
                    pricing_path=pricing,
                    run_id=self.run_id,
                ),
                ledger=self.ledger,
                pricing=load_pricing(pricing),
            )
        return WitnessCheckingPrivilegeJudge(
            logged_complete(self._judge_client, self.run_dir / "raw/judge"),
            config=judge_cfg,
            attribution=attribution,
        )

    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        if STOP.is_set():
            raise InfraError("Experiment stopped after another task failed", kind="experiment_stop")
        append_jsonl(
            self.run_dir / "physical_batches.jsonl",
            {
                "task_id": task.task_id,
                "phase": attribution.phase,
                "budget": attribution.budget,
                "n": n,
                "candidate_sha256": candidate_sha(candidate),
                "ts": time.time(),
            },
        )
        traces = super().rollouts(
            task, candidate, n, attribution=attribution, reset_options=reset_options
        )
        for trace in traces:
            append_jsonl(
                self.run_dir / "all_physical_traces.jsonl",
                {
                    "phase": attribution.phase,
                    "budget": attribution.budget,
                    "candidate_sha256": candidate_sha(candidate),
                    "trace": trace.model_dump(mode="json"),
                },
            )
        validate_returned_traces(traces, n, task.seed, candidate)
        physical_closed(physical_summary(self.run_dir / "physical"))
        emit(
            task=int(task.task_id),
            phase_category=(
                "estimate"
                if attribution.phase == "estimate"
                else "confirmation"
                if attribution.budget == "eval"
                else "adaptation"
            ),
            n=len(traces),
            successes=sum(bool(t.success) for t in traces),
            errors=sum(bool(t.error) for t in traces),
        )
        return traces


def build(task: int) -> AuditedSubstrate:
    directory = BASE / f"task-{task}"
    policy, designer = e3.policy_qwen(), e3.designer_deepseek()
    sub = AuditedSubstrate(
        corpus_yaml=ROOT / "configs/corpus_aea.yaml",
        run_dir=directory,
        run_id=f"e3-integrated-{task}",
        policy_llm=policy,
        designer_llm=designer,
        aea_config=config(),
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=ROLLOUT_CONCURRENCY,
        subprocess_timeout_s=600.0,
    )
    sub.policy_spec_kwargs["client_factory"] = "aea.llm.physical_audit:AuditedPolicyClient"
    sub.policy_spec_kwargs["client_kwargs"].update(
        audit_dir=str(directory / "physical"), run_id=sub.run_id
    )
    assert sub._designer is not None
    sub._designer._transport = AuditedTransport(
        sub._designer._transport,
        directory / "physical",
        config=designer,
        pricing_path=e3.PRICING,
        run_id=sub.run_id,
    )
    if sub.max_steps != 50:
        raise ConfigError("Frozen learner horizon mismatch")
    return sub


def validate_returned_traces(traces: list[Trace], n: int, seed: int, candidate: Candidate) -> None:
    if len(traces) != n:
        raise InfraError("Incomplete rollout batch", kind="rollout")
    errors = " ".join(str(trace.error or "") for trace in traces)
    if "provider_mismatch" in errors or "pricing_mismatch" in errors:
        raise ConfigError("Learner provenance or pricing guard failed")
    identifiers = [trace.episode_id for trace in traces]
    if not all(identifiers) or len(set(identifiers)) != n:
        raise ConfigError("Missing or duplicate fresh episode identity")
    for trace in traces:
        if not trace.error and (
            trace.rollout_seed != seed or candidate_sha(trace.candidate) != candidate_sha(candidate)
        ):
            raise ConfigError("Returned trace differs from dispatched task or candidate")
    with EPISODE_LOCK:
        if SEEN_EPISODES.intersection(identifiers):
            raise ConfigError("Episode identity reused across fresh batches")
        SEEN_EPISODES.update(identifiers)


def physical_closed(summary: dict[str, Any]) -> None:
    if any(summary[key] for key in ("inflight", "invalid_usage", "incomplete_journal_lines")):
        raise ConfigError("Physical accounting has unresolved or corrupt attempts")


def candidate_sha(candidate: Candidate) -> str:
    return digest(
        {
            "rules_code": candidate.rules_code or "",
            "in_env_actions": [a.model_dump(mode="json") for a in candidate.in_env_actions],
        }
    )


def verify_low_final(directory: Path, candidate: Candidate, dose: float) -> None:
    """Offline exact stored judge/source/dose binding, with no new judge call."""
    for row in rows(directory / "llm_privilege.jsonl"):
        record = JudgeRecord.model_validate(row["result"])
        evidence = PrivilegeJudgeInput.model_validate_json(
            gzip.decompress(Path(row["input_artifact"]).read_bytes())
        )
        validate_witness_record(record, evidence)
        if record.verdict != "PASS" or dose not in row["doses"]:
            continue
        template = evidence.candidate_artifact
        if hashlib.sha256(template.encode()).hexdigest() != record.source_sha256:
            raise ConfigError("Admitted source hash mismatch")
        if not isinstance(evidence.task_spec, dict):
            raise ConfigError("LOW admission task identity must be explicit")
        rendered = template.replace("__DOSE__", repr(float(dose))).replace(
            "__TASK_ID__", repr(str(evidence.task_spec["task_id"]))
        )
        if candidate.rules_code == rendered and not candidate.in_env_actions:
            return
    raise ConfigError("Final LOW candidate lacks exact stored R5 PASS for selected dose")


def verify_high_final(directory: Path, task: int, candidate: Candidate, dose: float) -> None:
    freezes = [
        row["payload"] for row in rows(directory / "events.jsonl") if row["kind"] == "family_frozen"
    ]
    if len(freezes) != 1 or freezes[0]["direction"] != "harder_with_d":
        raise ConfigError("HIGH final environment lacks one frozen family")
    source_sha = freezes[0]["source_sha256"]
    calls = rows(directory / "designer_calls.jsonl")
    if len(calls) != 1:
        raise ConfigError("HIGH must use exactly one designer call")
    accepted = calls[0].get("accepted_sources", [])
    if not any(item["source_sha256"] == source_sha for item in accepted):
        raise ConfigError("HIGH frozen source was not admitted by validation")
    for raw in calls[0]["arguments"].get("families", [])[:2]:
        if not isinstance(raw, dict):
            continue
        template = str(raw.get("rules_code") or "")
        if hashlib.sha256(template.encode()).hexdigest() != source_sha:
            continue
        rendered = template.replace("__DOSE__", repr(float(dose))).replace(
            "__TASK_ID__", repr(str(task))
        )
        if candidate.rules_code == rendered and not candidate.in_env_actions:
            return
    raise ConfigError("HIGH final candidate differs from its frozen source and selected dose")


class EvaluationSubstrate(Protocol):
    run_dir: Path

    def rollouts(
        self, task: TaskRef, candidate: Candidate, n: int, *, attribution: Attribution
    ) -> list[Trace]: ...


def confirm(sub: EvaluationSubstrate, task: int, outcome: dict[str, Any]) -> dict[str, Any]:
    directory = sub.run_dir
    if outcome["outcome"] not in ("accepted", "kept"):
        return {
            "status": "not_applicable",
            "successes": 0,
            "n": 0,
            "learnable": False,
            "target": False,
            "reused": False,
            "evidence_sha256": None,
        }
    entries = read_corpus(directory / "corpus.jsonl")
    if len(entries) != 1 or entries[0].aea.task_id != str(task):
        raise ConfigError("Accepted task must expose exactly one final environment")
    entry = entries[0]
    candidate = entry.to_candidate()
    if outcome["regime"] == "zero":
        if entry.aea.d is None:
            raise ConfigError("LOW final environment lacks selected dose")
        verify_low_final(directory, candidate, float(entry.aea.d))
    if outcome["regime"] == "saturated":
        if entry.aea.d is None:
            raise ConfigError("HIGH final environment lacks selected dose")
        verify_high_final(directory, task, candidate, float(entry.aea.d))
    if outcome["outcome"] == "kept" and candidate_sha(candidate) != candidate_sha(Candidate()):
        raise ConfigError("MID must return the original environment")
    before = method_state_sha256(directory)
    atomic_write_json(
        directory / "confirmation_started.json",
        {"method_state_sha256": before, "candidate_sha256": candidate_sha(candidate), "k": 16},
    )
    traces: list[Trace] = []
    for batch in range(4):
        returned = sub.rollouts(
            TaskRef(str(task), task),
            candidate,
            4,
            attribution=Attribution(
                phase=f"confirm_{batch}", budget="eval", arm=ARM, task_id=str(task)
            ),
        )
        for trace in returned:
            append_jsonl(directory / "confirmation_traces.jsonl", trace.model_dump(mode="json"))
        traces.extend(returned)
        if any(t.error for t in returned):
            raise InfraError("Confirmation episode error; no replacement or tuning", kind="rollout")
    if before != method_state_sha256(directory):
        raise ConfigError("K16 modified frozen method evidence")
    ids = [t.episode_id for t in traces]
    search_ids = {row["episode_id"] for row in rows(directory / "traces.jsonl")}
    if len(set(ids)) != 16 or set(ids) & search_ids:
        raise ConfigError("K16 episodes are not fresh and distinct")
    successes = sum(bool(t.success) for t in traces)
    return {
        "status": "completed",
        "successes": successes,
        "n": 16,
        "learnable": 4 <= successes <= 12,
        "target": 7 <= successes <= 9,
        "reused": False,
        "evidence_sha256": digest((directory / "confirmation_traces.jsonl").read_bytes()),
    }


def run_task(task: int) -> dict[str, Any]:
    directory = BASE / f"task-{task}"
    if (directory / "task_artifact.json").exists():
        artifact = read_json(directory / "task_artifact.json")
        if artifact["method_state_sha256"] != method_state_sha256(directory):
            raise ConfigError("Completed task method state changed")
        return public_task_metadata(artifact)
    if (directory / "started.json").exists():
        raise ConfigError(
            f"Task {task} already started without terminal artifact; audit before resume"
        )
    if STOP.is_set():
        return {"task_id": task, "status": "not_started"}
    atomic_write_json(
        directory / "started.json",
        {"ts": time.time(), "freeze_sha256": digest(FROZEN.read_bytes())},
    )
    emit(task=task, stage="started")
    try:
        sub = build(task)
        ctrl = Controller(
            config(),
            sub,
            directory,
            sub.run_id,
            arm=ARM,
            reference=sub.reference_provider(config()),
        )
        outcome = asdict(ctrl.run([TaskRef(str(task), task)])[0])
        atomic_write_json(directory / "outcome.json", outcome)
        if (
            outcome["outcome"] == "infra_error"
            or outcome["detail"].get("design_status") == "inconclusive"
        ):
            raise InfraError("Method ended with an infrastructure failure", kind="method")
        physical_closed(physical_summary(directory / "physical"))
        before = method_state_sha256(directory)
        k16 = confirm(sub, task, outcome)
        atomic_write_json(directory / "confirmation.json", k16)
        merge_ledgers(directory, sub.run_id)
        physical_closed(physical_summary(directory / "physical"))
        artifact = build_task_artifact(
            directory,
            str(task),
            k16=k16,
            physical_accounting=physical_summary(directory / "physical"),
            frozen_method_sha256=before,
        )
        atomic_write_json(directory / "task_artifact.json", artifact)
        public = public_task_metadata(artifact)
        atomic_write_json(directory / "task_metadata.json", public)
        emit(
            task=task,
            stage="completed",
            outcome=outcome["outcome"],
            regime=outcome["regime"],
            search_rollouts=outcome["n_search"],
            k16_successes=k16["successes"],
            k16_n=k16["n"],
        )
        return public
    except BaseException as exc:
        STOP.set()
        atomic_write_json(
            directory / "interruption.json",
            {"type": type(exc).__name__, "message": str(exc), "ts": time.time()},
        )
        emit(task=task, stage="interrupted", error_type=type(exc).__name__)
        raise


def probe() -> None:
    directory = BASE / "endpoint_probe"
    if (directory / "result.json").exists():
        return
    if (directory / "started.json").exists():
        raise ConfigError("Interrupted endpoint probe requires audit")
    atomic_write_json(directory / "started.json", {"ts": time.time()})
    llm = e3.policy_qwen()
    client = OpenAICompatibleClient(
        config=llm,
        transport=AuditedTransport(
            make_openai_transport(
                api_key=load_settings(ROOT / ".env").require(llm.api_key_env.lower()),
                base_url=llm.base_url,
                timeout_s=llm.timeout_s,
            ),
            directory / "physical",
            config=llm,
            pricing_path=e3.PRICING,
            run_id="e3-integrated-probe",
        ),
        ledger=Ledger(directory / "ledger.jsonl", "e3-integrated-probe"),
        pricing=load_pricing(e3.PRICING),
    )
    response = logged_complete(client, directory / "raw")(
        ChatRequest(
            model=llm.model,
            temperature=llm.temperature,
            max_tokens=16,
            seed=0,
            messages=(ChatMessage(role="user", content="Reply OK."),),
            attribution=Attribution(
                phase="endpoint_probe", budget="none", arm=ARM, task_id="probe"
            ),
        )
    )
    atomic_write_json(
        directory / "result.json",
        {
            "provider": response.provider,
            "request_sha256": response.request_sha256,
            "response_sha256": digest(response.model_dump(mode="json")),
        },
    )
    physical_closed(physical_summary(directory / "physical"))
    emit(stage="endpoint_probe_passed", provider=response.provider)


def run() -> None:
    ensure_frozen(paid=True)
    os.umask(0o077)
    default_env_config = (
        ROOT / "third_party/envharness/envharness/third_party/alfworld/base_config.yaml"
    )
    override = os.environ.get("ALFWORLD_CONFIG")
    if override and Path(override).resolve() != default_env_config.resolve():
        raise ConfigError("ALFWORLD_CONFIG differs from the frozen original E3 environment")
    os.environ["ALFWORLD_CONFIG"] = str(default_env_config)
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / "execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
        os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
        if not (BASE / "manifest.json").exists():
            atomic_write_json(
                BASE / "manifest.json",
                {
                    "protocol": PROTOCOL,
                    "git_sha": git("rev-parse", "HEAD"),
                    "freeze_sha256": digest(FROZEN.read_bytes()),
                    "usd_cap": None,
                    "authorization": (
                        "User requested complete AEA integration and E3 without a budget ceiling"
                    ),
                    "recipients": ["https://api.deepseek.com", "https://openrouter.ai/api/v1"],
                    "tasks": list(TASKS),
                    "created_at": time.time(),
                },
            )
        elif read_json(BASE / "manifest.json")["freeze_sha256"] != digest(FROZEN.read_bytes()):
            raise ConfigError("Existing experiment binds another freeze")
        probe()
        shared = read_json(OLD)["shared"]
        order = sorted(TASKS, key=lambda t: (shared[str(t)]["p16"], t))
        with cf.ThreadPoolExecutor(max_workers=TASK_CONCURRENCY) as pool:
            futures = {pool.submit(run_task, task): task for task in order}
            failures = []
            for future in cf.as_completed(futures):
                try:
                    future.result()
                except BaseException as exc:
                    STOP.set()
                    failures.append({"task_id": futures[future], "type": type(exc).__name__})
        atomic_write_json(
            BASE / "execution_status.json",
            {"complete": not failures, "failures": failures, "ts": time.time()},
        )
        if failures:
            raise InfraError(
                "E3 stopped; inspect private interruptions before any restart", kind="experiment"
            )
        emit(stage="all_tasks_complete", tasks=30)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "run", "audit", "report"))
    args = parser.parse_args()
    if args.stage == "freeze":
        freeze()
    elif args.stage == "run":
        run()
    else:
        from scripts.make_tables_e3_integrated import audit, report

        (audit if args.stage == "audit" else report)()


if __name__ == "__main__":
    main()
