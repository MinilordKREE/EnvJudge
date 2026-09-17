"""Offline integrity audit and metadata-only comparison for the new complete AEA arm."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate
from scripts import e3_integrated as run

from aea.core.io import atomic_write_json, atomic_write_text, read_json
from aea.errors import ConfigError
from aea.integrated_artifacts import build_task_artifact, method_state_sha256, public_task_metadata
from aea.io import read_corpus
from aea.llm.physical_audit import physical_summary
from aea.privilege_judge import JudgeRecord, PrivilegeJudgeInput
from aea.privilege_witness import validate_witness_record

RESULTS = run.EXP / "results/integrated_aea"
REPORT = run.EXP / "INTEGRATED_AEA_REPORT.md"


def rate(
    envs: list[dict[str, Any]], charges: dict[str, int], tasks: list[str], rng: random.Random
) -> dict[str, Any]:
    """Same task bootstrap and denominator as original E3; all new search costs count."""
    learn = Counter(str(e["task"]) for e in envs if e["learnable"] and str(e["task"]) in tasks)
    count = sum(str(e["task"]) in tasks for e in envs)
    total = sum(charges.get(t, 0) for t in tasks)
    boots = []
    for _ in range(10_000):
        sample = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        den = sum(charges.get(t, 0) for t in sample)
        boots.append(1000 * sum(learn.get(t, 0) for t in sample) / den if den else 0.0)
    boots.sort()
    return {
        "envs": count,
        "learnable": sum(learn.values()),
        "rollouts": total,
        "tasks": len(tasks),
        "per_1000": 1000 * sum(learn.values()) / total if total else None,
        "ci95": [boots[250], boots[9750]],
    }


def audit() -> dict[str, Any]:
    run.ensure_frozen()
    checks = 0

    def check(ok: bool, label: str) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            raise ConfigError("Integrated E3 audit failed: " + label)

    status = read_json(run.BASE / "execution_status.json")
    check(status["complete"] and not status["failures"], "all task execution complete")
    all_ids: set[str] = set()
    all_metadata = []
    aggregate: Counter[str] = Counter()
    logical_usd = 0.0
    physical_totals: dict[str, float] = {}
    for task in run.TASKS:
        directory = run.BASE / f"task-{task}"
        stored = read_json(directory / "task_artifact.json")
        confirmation = read_json(directory / "confirmation.json")
        physical = physical_summary(directory / "physical")
        expected = build_task_artifact(
            directory,
            str(task),
            k16=confirmation,
            physical_accounting=physical,
            frozen_method_sha256=stored["method_state_sha256"],
        )
        check(expected == stored, "unified task artifact reproduces")
        public = public_task_metadata(stored)
        check(public == read_json(directory / "task_metadata.json"), "public projection reproduces")
        all_metadata.append(public)
        events = [(row["kind"], row["payload"]) for row in run.rows(directory / "events.jsonl")]
        done = [p for kind, p in events if kind == "task_done"]
        check(len(done) == 1 and done[0]["outcome"] != "infra_error", "one completed task attempt")
        outcome = done[0]
        check(0 <= outcome["baseline_rollouts"] <= 16, "baseline cap")
        check(0 <= outcome["adaptation_rollouts"] <= 30, "adaptation cap")
        check(
            outcome["n_search"] == outcome["baseline_rollouts"] + outcome["adaptation_rollouts"],
            "search includes baseline and adaptation",
        )
        measurement = [p for kind, p in events if kind == "measurement_evidence"]
        check(len(measurement) == 1, "measurement evidence exists")
        m = measurement[0]
        check(
            outcome["regime"] == max(m["probabilities"], key=m["probabilities"].get),
            "posterior regime classification",
        )
        check(m["p_hat"] == m["successes"] / m["n"], "baseline raw estimate")
        designers = run.rows(directory / "designer_calls.jsonl")
        check(len(designers) <= (3 if outcome["regime"] == "zero" else 1), "designer bound")
        if outcome["regime"] == "band":
            check(
                not designers
                and not stored["privilege_decisions"]
                and not stored["privileged_references"],
                "MID no design/reference/judge",
            )
            check(
                outcome["adaptation_rollouts"] == 0 and outcome["outcome"] == "kept",
                "MID original with no adaptation",
            )
        freeze = [p for kind, p in events if kind == "family_frozen"]
        check(len(freeze) <= 1, "at most one viable semantic family")
        doses = [p for kind, p in events if kind in {"endpoint", "dose_evaluation"}]
        if freeze:
            check(bool(doses), "viable family has endpoint evidence")
            frozen = freeze[0]
            position = next(i for i, (kind, _) in enumerate(events) if kind == "family_frozen")
            check(
                not any(kind == "designer_evidence" for kind, _ in events[position + 1 :]),
                "no design after freeze",
            )
            check(
                all(
                    p.get("family") == frozen["family"]
                    for kind, p in events[position + 1 :]
                    if kind in {"dose_control", "bracket", "endpoint", "dose_evaluation"}
                ),
                "control family unchanged",
            )
            check(
                all(
                    p.get("source_sha256") == frozen["source_sha256"]
                    for kind, p in events[position + 1 :]
                    if kind == "dose_evaluation"
                ),
                "CONTROL source hash unchanged",
            )
        for endpoint in doses:
            n, s, verdict = endpoint["n"], endpoint["s"], endpoint["verdict"]
            check((n == 4 and s in (0, 4)) or (n == 8 and 0 <= s <= 8), "4-to-8 semantics")
            check((verdict == "in_band") == (n == 8 and 3 <= s <= 5), "fixed search acceptance")
        decisions = {}
        admitted_renderings = set()
        for row in stored["privilege_decisions"]:
            record = JudgeRecord.model_validate(row["result"])
            evidence = PrivilegeJudgeInput.model_validate_json(
                gzip.decompress(Path(row["input_artifact"]).read_bytes())
            )
            check(
                hashlib.sha256(evidence.candidate_artifact.encode()).hexdigest()
                == record.source_sha256,
                "judge source binding",
            )
            check(
                run.digest(evidence.model_dump(mode="json")) == record.input_sha256,
                "judge exact complete input",
            )
            validate_witness_record(record, evidence)
            checks += 1
            decisions[record.source_sha256] = record.verdict
            if record.verdict == "PASS":
                for dose in row["doses"]:
                    rendered = evidence.candidate_artifact.replace(
                        "__DOSE__", repr(float(dose))
                    ).replace("__TASK_ID__", repr(str(task)))
                    admitted_renderings.add(run.candidate_sha(Candidate(rules_code=rendered)))
            aggregate["judge_decisions"] += 1
            aggregate["judge_" + record.verdict] += 1
        for candidate in stored["candidate_lineage"]:
            if outcome["regime"] == "zero" and candidate["endpoint"] is not None:
                check(
                    decisions.get(candidate["source_sha256"]) == "PASS", "only PASS reaches policy"
                )
            if outcome["regime"] == "zero" and candidate["privilege"]:
                check(
                    candidate["solvability"] is None and candidate["endpoint"] is None,
                    "privilege rejection precedes certification and policy",
                )
        physical_traces = run.rows(directory / "all_physical_traces.jsonl")
        planned = run.rows(directory / "physical_batches.jsonl")
        check(sum(r["n"] for r in planned) == len(physical_traces), "physical batches reconcile")
        valid_search = [
            r for r in physical_traces if r["budget"] == "search" and not r["trace"]["error"]
        ]
        check(len(valid_search) == outcome["n_search"], "every valid search episode charged")
        search_ids = {r["episode_id"] for r in run.rows(directory / "traces.jsonl")}
        eval_traces = run.rows(directory / "confirmation_traces.jsonl")
        check(not search_ids & {r["episode_id"] for r in eval_traces}, "K16 independent of search")
        for row in physical_traces:
            trace = row["trace"]
            check(trace["episode_id"] not in all_ids, "unique fresh episode IDs across experiment")
            all_ids.add(trace["episode_id"])
            check(str(trace["rollout_seed"]) == str(task), "episode task seed binding")
            check(
                run.candidate_sha(Candidate.model_validate(trace["candidate"]))
                == row["candidate_sha256"],
                "returned candidate matches physical dispatch",
            )
            aggregate["physical_policy_episodes"] += 1
        for row in planned:
            if outcome["regime"] == "zero" and row["phase"] != "estimate":
                check(
                    row["candidate_sha256"] in admitted_renderings,
                    "every LOW policy batch binds a PASS source and captured dose",
                )
            if row["phase"] == "estimate":
                check(
                    row["candidate_sha256"] == run.candidate_sha(Candidate()),
                    "original baseline",
                )
        ledger = run.rows(directory / "ledger.jsonl")
        ledger_rollouts = [r for r in ledger if r["event"] == "rollout"]
        check(
            {r["rollout_uid"] for r in ledger_rollouts}
            == {r["trace"]["episode_id"] for r in physical_traces}
            and len(ledger_rollouts) == len(physical_traces),
            "rollout ledger complete and unique",
        )
        logical_calls = [r for r in ledger if r["event"] == "call"]
        check(
            len(logical_calls) <= physical["returned"], "logical calls covered by physical returns"
        )
        check(
            physical["inflight"] == 0
            and physical["invalid_usage"] == 0
            and physical["incomplete_journal_lines"] == 0,
            "physical journals closed with valid usage",
        )
        if confirmation["status"] == "completed":
            check(
                len(eval_traces) == 16 and all(not t["error"] for t in eval_traces), "complete K16"
            )
            check(
                sum(bool(t["success"]) for t in eval_traces) == confirmation["successes"],
                "K16 counts",
            )
            binding = read_json(directory / "confirmation_started.json")
            check(
                binding["method_state_sha256"] == method_state_sha256(directory),
                "K16 immutable method",
            )
            check(
                run.digest((directory / "confirmation_traces.jsonl").read_bytes())
                == confirmation["evidence_sha256"],
                "K16 trace file digest",
            )
            if outcome["regime"] == "zero":
                entry = read_corpus(directory / "corpus.jsonl")[0]
                check(entry.aea.d is not None, "LOW selected dose exists")
                assert entry.aea.d is not None
                run.verify_low_final(directory, entry.to_candidate(), float(entry.aea.d))
                checks += 1
            elif outcome["regime"] == "saturated":
                entry = read_corpus(directory / "corpus.jsonl")[0]
                check(entry.aea.d is not None, "HIGH selected dose exists")
                assert entry.aea.d is not None
                run.verify_high_final(directory, task, entry.to_candidate(), float(entry.aea.d))
                checks += 1
        else:
            check(not eval_traces and outcome["outcome"] == "dropped", "no K16 for dropped task")
        aggregate["baseline_rollouts"] += outcome["baseline_rollouts"]
        aggregate["adaptation_rollouts"] += outcome["adaptation_rollouts"]
        aggregate["confirmation_rollouts"] += len(eval_traces)
        aggregate["designer_calls"] += len(designers)
        aggregate["logical_calls"] += len(logical_calls)
        logical_usd += sum(r["usd"] for r in logical_calls)
        for key, value in physical.items():
            if isinstance(value, (int, float)):
                physical_totals[key] = physical_totals.get(key, 0.0) + value
    # Verify physical raw artifacts separately, including the pre-arm routing probe.
    for journal in sorted(run.BASE.rglob("physical/attempts.*.jsonl")):
        for row in run.rows(journal):
            if row["status"] == "started":
                path = journal.parent / row["raw_request_file"]
                check(
                    run.digest(path.read_bytes()) == row["raw_request_sha256"],
                    "physical raw request hash",
                )
                check(
                    row["recipient"]
                    in ("https://api.deepseek.com", "https://openrouter.ai/api/v1"),
                    "authorized recipient",
                )
                if row["model"] == "qwen/qwen3-8b":
                    check(row["provider_pin"] == "alibaba", "frozen learner endpoint pin")
            elif row["status"] == "returned":
                path = journal.parent / row["raw_response_file"]
                check(
                    run.digest(path.read_bytes()) == row["raw_response_sha256"],
                    "physical raw response hash",
                )
    probe_dir = run.BASE / "endpoint_probe"
    probe_physical = physical_summary(probe_dir / "physical")
    check(probe_physical["inflight"] == 0, "probe physically closed")
    probe_calls = [r for r in run.rows(probe_dir / "ledger.jsonl") if r["event"] == "call"]
    aggregate["logical_calls"] += len(probe_calls)
    logical_usd += sum(r["usd"] for r in probe_calls)
    for key, value in probe_physical.items():
        if isinstance(value, (int, float)):
            physical_totals[key] = physical_totals.get(key, 0.0) + value
    result = {
        "status": "PASS",
        "protocol": run.PROTOCOL,
        "checks": checks,
        "tasks": 30,
        "freeze_sha256": run.digest(run.FROZEN.read_bytes()),
        "task_metadata_sha256": run.digest(all_metadata),
        "accounting": dict(aggregate),
        "logical_usd": logical_usd,
        "physical_accounting": dict(physical_totals),
        "limitations": [
            "Stored evidence and execution integrity; no proof of judge semantic accuracy",
            "Physical attempts identify process/task/phase; provider receipt does not expose "
            "episode UUID",
            "Ambiguous transport failures retain estimates, not asserted provider charges",
        ],
    }
    atomic_write_json(run.BASE / "execution_audit.json", result)
    run.emit(stage="offline_audit_passed", checks=checks, tasks=30)
    return result


def report() -> dict[str, Any]:
    verified = audit()
    old = read_json(run.OLD)
    metadata = [read_json(run.BASE / f"task-{task}/task_metadata.json") for task in run.TASKS]
    envs = [
        {
            "task": str(m["task_id"]),
            "learnable": m["k16"]["learnable"],
            "kind": m["final_environment"]["kind"],
        }
        for m in metadata
        if m["final_environment"]
    ]
    transformed = [e for e in envs if e["kind"] != "kept"]
    charges = {str(m["task_id"]): m["rollout_accounting"]["search_charged"] for m in metadata}
    tasks = [str(t) for t in run.TASKS]
    rng = random.Random(20260911)
    primary = rate(envs, charges, tasks, rng)
    secondary = rate(transformed, charges, tasks, rng)
    saturated = rate(transformed, charges, old["classes"]["saturated"], rng)
    learnable = {e["task"] for e in envs if e["learnable"]}
    unlocked = sorted(learnable & set(old["classes"]["zero"]), key=int)
    preserved = sorted(learnable & set(old["classes"]["band"]), key=int)
    old_primary = {
        arm: {
            k: v
            for k, v in old["primary"][arm].items()
            if k in {"envs", "learnable", "rollouts", "tasks", "per_1000", "ci95"}
        }
        for arm in ("A", "G", "R")
    }
    result = {
        "protocol": run.PROTOCOL,
        "implementation_commit": read_json(run.BASE / "manifest.json")["git_sha"],
        "historical_data_sha256": run.digest(run.OLD.read_bytes()),
        "usd_cap": None,
        "budget_matched_to_original_e3": False,
        "judge_phase_a_ready": False,
        "primary": primary,
        "transformed_only": secondary,
        "saturated_subset": saturated,
        "preserved": preserved,
        "unlocked": unlocked,
        "precision": [sum(e["learnable"] for e in transformed), len(transformed)],
        "historical_primary": old_primary,
        "original": {"environments": 30, "learnable": 6, "search_rollouts": 0, "per_1000": None},
        "regimes": dict(Counter(m["regime"] for m in metadata)),
        "outcomes": dict(Counter(m["outcome"] for m in metadata)),
        "target_k16_count": sum(m["k16"]["target"] for m in metadata),
        "execution_audit": verified,
        "tasks": metadata,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(RESULTS / "report.json", result)
    atomic_write_json(RESULTS / "execution_audit.json", verified)
    atomic_write_json(RESULTS / "task_metadata.json", metadata)

    def fmt_rate(row: dict[str, Any]) -> str:
        return f"{row['per_1000']:.2f} [{row['ci95'][0]:.2f}, {row['ci95'][1]:.2f}]"

    lines = [
        "# E3 complete AEA integration — layer-one performance",
        "",
        f"Implementation: `{result['implementation_commit']}`. All30 existing tasks completed; "
        f"offline execution audit **PASS ({verified['checks']} checks)**.",
        "",
        "The new arm uses fresh baseline≤16 plus adaptation≤30, with all search episodes "
        "in the denominator. "
        "Historical R/G/AEA v0.2 use their original cap30 including baseline. This "
        "comparison is not budget matched. "
        "Models/settings and cohort are retained, but API execution occurs later. No old "
        "arm was rerun.",
        "",
        "## Learner-facing environments",
        "",
        "| Arm | Environments | K16 learnable | Search episodes | Learnable /1000 [95% "
        "task bootstrap CI] |",
        "|---|---:|---:|---:|---|",
        "| O |30|6|0|undefined|",
    ]
    for key, label in (("R", "R"), ("G", "G"), ("A", "AEA v0.2")):
        row = old_primary[key]
        lines.append(
            f"|{label}|{row['envs']}|{row['learnable']}|{row['rollouts']}|{fmt_rate(row)}|"
        )
    lines += [
        f"|AEA integrated|{primary['envs']}|{primary['learnable']}|"
        f"{primary['rollouts']}|{fmt_rate(primary)}|",
        "",
        "K16 learnable means 4-12/16 successes; search acceptance remains 3-5/8. Fresh "
        "confirmations also cover kept MID tasks. "
        "O productivity is undefined because its search charge is zero.",
        "",
        "## Adaptation and coverage",
        "",
        f"- Transformed-only: {secondary['learnable']}/{secondary['envs']} learnable; "
        f"{fmt_rate(secondary)} per1000 search episodes.",
        f"- Original-zero unlocks: {len(unlocked)} ({', '.join(unlocked) or 'none'}). "
        f"Historical G:1; AEA v0.2:0; R:0.",
        f"- Original-band preservation: {len(preserved)}/6. Narrow B_T confirmations: "
        f"{result['target_k16_count']}.",
        f"- Saturated-subset transformed productivity: {fmt_rate(saturated)} per1000.",
        f"- Fresh measurement regimes: {json.dumps(result['regimes'], sort_keys=True)}.",
        "",
        "## Accounting and interpretation",
        "",
        f"Baseline {verified['accounting']['baseline_rollouts']}; adaptation "
        f"{verified['accounting']['adaptation_rollouts']}; "
        f"confirmation {verified['accounting']['confirmation_rollouts']} episodes. "
        f"Logical returned-call cost **USD {verified['logical_usd']:.6f}** including the "
        f"endpoint probe. "
        f"Physical conservative total **USD "
        f"{verified['physical_accounting']['conservative_total_usd']:.6f}**, "
        f"including retained ambiguous-attempt estimates. No monetary cap.",
        "",
        "LOW uses the unchanged R5 judge. Its historical Phase A remains NOT_READY; "
        "candidate PASS is admission, "
        "not a leakage ground-truth label. This evaluates integrated operation and "
        "environment productivity on a reused "
        "cohort, without isolating iterative feedback causally. No post-K16 redesign or "
        "judge retuning occurred.",
        "",
        "Full references, requests/responses, candidate code and surfaces remain local/gitignored. "
        "Public JSON contains allowlisted numeric/category/hash metadata. See the prospective "
        "[protocol](PREREG_INTEGRATED_AEA.md) and [machine-readable "
        "report](results/integrated_aea/report.json).",
        "",
        "## Per-task results",
        "",
        "| Task | Regime | Outcome | Designer calls | Search episodes | K16 | Learnable |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for m in metadata:
        k = m["k16"]
        kn = f"{k['successes']}/{k['n']}" if k["n"] else "—"
        lines.append(
            f"|{m['task_id']}|{m['regime']}|{m['outcome']}|{m['designer_calls']['count']}|"
            f"{m['rollout_accounting']['search_charged']}|{kn}|{k['learnable']}|"
        )
    atomic_write_text(REPORT, "\n".join(lines) + "\n")
    run.emit(
        stage="report_complete",
        environments=primary["envs"],
        learnable=primary["learnable"],
        per_1000=primary["per_1000"],
        logical_usd=verified["logical_usd"],
    )
    return result


if __name__ == "__main__":
    report()
