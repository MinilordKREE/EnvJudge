"""P5.5 analysis → p5/results/report.md: header (PREREG5 sha, config sha256s, spend), P5.1 learnability profiles + K5, P5.2 H5,
P5.3 bank-size curve, P5.4 summary, measurement notes, caveats."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
for p in (ROOT, EOBS, ROOT / "p4", ROOT / "p5"):
    sys.path.insert(0, str(p))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402

RES = ROOT / "p5" / "results"
LED = ROOT / "results" / "e1pilot" / "ledger.jsonl"


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def _csv(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p))) if Path(p).exists() else []


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def spend() -> dict[str, float]:
    by = defaultdict(float)
    for l in open(LED):
        try:
            r = json.loads(l)
        except Exception:
            continue
        by[r.get("phase") or ""] += float(r.get("usd") or 0)
    return dict(by)


def paired(rows, a, b, split):
    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["split"] == split and r["condition"] in (a, b):
            per[r["seed"]][r["condition"]].append(int(r["success"] in ("True", True)))
    d = {s: sum(c[a]) / len(c[a]) - sum(c[b]) / len(c[b]) for s, c in per.items() if c.get(a) and c.get(b)}
    if not d:
        return None
    x = np.array(list(d.values())); idx = np.random.default_rng(20260906).integers(0, len(x), size=(10000, len(x))); m = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), len(d)


def rate(rows, cond, split):
    g = defaultdict(list)
    for r in rows:
        if r["condition"] == cond and r["split"] == split:
            g[r["seed"]].append(r)
    return boot_rate(g, lambda r: r["success"] in ("True", True), lambda r: 1) if g else None


def ps(t):
    return "n/a" if t is None else f"{fmt(t[0])} [{fmt(t[1])}, {fmt(t[2])}] (n={t[3]})"


def main(prereg_sha: str) -> None:
    sp = spend(); p5 = {k: round(v, 2) for k, v in sp.items() if k.startswith("p5")}
    cfg100 = ROOT / "p5" / "configs" / "alfworld_config_100.yaml"
    base = ROOT.parent.parent / "third_party" / "envharness" / "envharness" / "third_party" / "alfworld" / "base_config.yaml"
    evalcfg = yaml.safe_load((ROOT / "configs" / "reasoning_bank_eval_qwen.yaml").read_text())
    topk = evalcfg.get("retrieval", {}).get("top_k", evalcfg.get("bank", {}).get("top_k", "?"))
    L = [f"# P5 report — CHS fork test, induction-mode control, bank-size dose — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
         f"PREREG5 sha `{prereg_sha}`; inputs P4 @ b22f07d; config sha256 (16 hex): vendored base_config `{sha(base)}`, alfworld_config_100 `{sha(cfg100)}`; "
         f"policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, 0.117/0.455 USD/M); induction DeepSeek V4 Pro; "
         f"P5 spend USD {round(sum(p5.values()), 2)} of 35 ({p5}); pilot total USD {round(sum(sp.values()), 2)} (hard 150 / soft 130).", ""]
    # ---------- P5.1
    certs = _jsonl(RES / "chs_certs.jsonl"); old = _jsonl(ROOT / "p4" / "results" / "nzero_states.jsonl")
    def lany(rows):
        c = defaultdict(lambda: defaultdict(list))
        for r in rows:
            c[(r["task_id"], r["episode_id"])][r["t"]].append(r["C"])
        return {k: (max([t for t, cs in v.items() if any(cs) and t > 0], default=0), sum(1 for t, cs in v.items() if any(cs) and t > 0)) for k, v in c.items()}
    new_l, old_l = lany(certs), lany(old)
    L += ["## P5.1 Certified Hindsight Staging with the re-based budget (100-config; policy budget 50)", "",
          "Certificates C_any3 recomputed for every prefix of the 24 P4.2 trajectories (expert ≤ 50 own steps). L_any3 = latest certified state; 'certified states' counts t > 0.", "",
          "| task | trajectory | L_any3 (P4, residual budget) | L_any3 (P5, 100-config) | certified states P4 → P5 |", "|---|---|---|---|---|"]
    gained = 0
    for k in sorted(new_l, key=lambda k: (k[0], k[1])):
        o = old_l.get(k, (0, 0)); n = new_l[k]; gained += max(n[1] - o[1], 0)
        L.append(f"| {k[0]} | {k[1][:8]} | {o[0]} | {n[0]} | {o[1]} → {n[1]} |")
    L += ["", f"States that gained a certificate under the 100-config: {gained} (sum over trajectories of the increase in certified-state counts).", ""]
    prof = _csv(RES / "chs_profile.csv"); sel = _csv(RES / "chs_selected.csv")
    if prof:
        L += ["### Learnability profiles p̂_4(t) — ALL candidates probed (4 corpus-protocol rollouts each; 0/4 dead, 4/4 saturated, 1–3 learnable)", "",
              "| task | t (kind): successes/4 … | learnable | dead | saturated | earliest learnable t | selected t | p̂_12 | confirmed | status |", "|---|---|---|---|---|---|---|---|---|---|"]
        by = defaultdict(list)
        for r in prof:
            by[r["task_id"]].append(r)
        for s in sorted(sel, key=lambda r: int(r["task_id"])):
            rows = sorted(by.get(s["task_id"], []), key=lambda r: -int(r["t"]))
            L.append(f"| {s['task_id']} | " + " ".join(f"{r['t']}({r['kind']}):{r['probe_successes']}/4" for r in rows) + f" | {s['n_learnable']} | {s['n_dead']} | {s['n_saturated']} | {s['earliest_learnable_t']} | {s['selected_t']} | {s['p12']} | {s['confirmed']} | {s['status']} |")
        k5 = sum(r["confirmed"] == "True" for r in sel)
        verdict = "≥ 4 → zero side alive: CHS is the primary operator of the method" if k5 >= 4 else ("2–3 → marginal: the design meeting decides with the profiles in hand" if k5 >= 2 else "≤ 1 → CHS has no working targets for this policy on this substrate")
        L += ["", f"**K5: {k5}/8 zero tasks with a confirmed selected env (p̂_12 ∈ [0.2, 0.8]) → {verdict}.**", ""]
    else:
        L += ["(probe not run yet)", ""]
    # ---------- P5.2 / P5.3
    ev = _csv(RES / "evals_p5.csv"); meta = json.loads((RES / "induce_ss.json").read_text()) if (RES / "induce_ss.json").exists() else {}
    if ev:
        L += ["## P5.2 Induction-mode control (single_succ on both sides; matched items)", "",
              f"Banks: isat_ss {meta.get('isat_ss', {}).get('items', '?')} items, origc_isat_ss {meta.get('origc_isat_ss', {}).get('items', '?')} items, all single_succ; matched = {meta.get('matched_items', '?')} (seed 20260914).", "",
              "| condition | ID | OOD |", "|---|---|---|"]
        for c in ("nobank", "orig_m", "isat_m", "origc_isat_m", "isat_ss", "origc_isat_ss"):
            a, b = rate(ev, c, "eval_in_distribution"), rate(ev, c, "eval_out_of_distribution")
            if a or b:
                L.append(f"| {c} | {rs(a) if a else 'n/a'} | {rs(b) if b else 'n/a'} |")
        h5 = paired(ev, "isat_ss", "origc_isat_ss", "eval_in_distribution")
        if h5 is None:
            out = "not evaluable"
        elif h5[0] >= -0.05:
            out = "H5a: environment content not shown harmful; the P3/P4 deficits are attributed to induction mode and bank size; the interface/Goodhart claim is withdrawn from the method's claims"
        elif h5[2] < 0:
            out = "H5b: interface-environment content is harmful even in success-only induction; the claim survives at pilot grade"
        else:
            out = "inconclusive (difference < −0.05 but the 95% CI includes 0)"
        L += ["", f"**H5 (isat_ss(m) − origc_isat_ss(m), ID, paired): {ps(h5)} → {out}.** OOD: {ps(paired(ev, 'isat_ss', 'origc_isat_ss', 'eval_out_of_distribution'))}; "
              f"P4 paired-diff comparison for reference: isat_m − origc_isat_m ID {ps(paired(ev, 'isat_m', 'origc_isat_m', 'eval_in_distribution'))}.", "",
              f"vs nobank (ID): isat_ss {ps(paired(ev, 'isat_ss', 'nobank', 'eval_in_distribution'))}; origc_isat_ss {ps(paired(ev, 'origc_isat_ss', 'nobank', 'eval_in_distribution'))}.", ""]
        L += ["## P5.3 Bank-size dose on orig_m (single_succ items; seeded subsamples 20260915)", "",
              f"Retrieval: top_k = {topk} ({evalcfg.get('retrieval', {}).get('mode', '?')}); banks with ≤ top_k items inject every item on every step (marked ★).", "",
              "| bank size | ID | OOD | ID − nobank | OOD − nobank |", "|---|---|---|---|---|"]
        for k, c in ((3, "orig_m_k3"), (6, "orig_m_k6"), (9, "orig_m_k9"), (15, "orig_m_k15"), (23, "orig_m")):
            a, b = rate(ev, c, "eval_in_distribution"), rate(ev, c, "eval_out_of_distribution")
            if a:
                mark = " ★" if isinstance(topk, int) and k <= topk else ""
                L.append(f"| {k}{mark} | {rs(a)} | {rs(b) if b else 'n/a'} | {ps(paired(ev, c, 'nobank', 'eval_in_distribution'))} | {ps(paired(ev, c, 'nobank', 'eval_out_of_distribution'))} |")
        a = rate(ev, "nobank", "eval_in_distribution"); b = rate(ev, "nobank", "eval_out_of_distribution")
        L += [f"| 0 (nobank) | {rs(a)} | {rs(b)} | — | — |", ""]
    # ---------- P5.4
    L += ["## P5.4 RL Phase-A audit (p5/docs/rl_audit.md)", "",
          "verl-agent (GiGPO; Apache-2.0) @ 796ed310 on verl, GRPO; env route `envharness_rl/alfworld` = Ray actors holding one AlfworldEnv each, Rules composed per episode, S0 replayed in place (no Setup/Link; prefix charged to the step cap); reward 10 × won with a 0.1 invalid-action penalty; released hardware 2 GPUs (smoke, Qwen2.5-1.5B) / 8 GPUs (full, Qwen3-8B, 128 episodes per step, 150 steps). The 100-config reaches the bridge only through $ALFWORLD_CONFIG exported after the launcher's own export, i.e. a launcher copy outside third_party.", "",
          "| run (1 × 80 GB GPU, Qwen3-8B + LoRA, 64 episodes/step, 30-step horizon, 150 steps) | GPU-hours (est.) | cloud USD at 2.5/h (est.) | wall time |", "|---|---|---|---|",
          "| A original env | 25–40 | 65–100 | 1–2 days |", "| B staged curriculum (P5.1 prefixes, 100-config) | 25–40 | 65–100 | 1–2 days |", "| full released recipe, 8×H100, per run | ~320 | ~800 | ~40 h |", "",
          "## Measurement notes", "",
          "- Every staged session (certificates, probes, bank rollouts) used the 100-config via reset_options.config_path; the LLM-free replay check gave 12 policy steps (default) vs 62 (copy) after a 38-action prefix. Unstaged sessions and all held-out evals use the default config.",
          "- P5.1 probed every candidate (no walk rule); selection = latest learnable; p̂_12 pools the 4 probe and 8 bank rollouts.",
          "- P5.2 induction = released `_build_bank` fed success-only trajectories, so `_pick_pair` yields the shortest success and `induce_memory_items(success=True)` runs on both sides; P5.3 subsamples the P3b orig_m bank without re-induction.",
          "- Held-out evals: released protocol, 30 ID + 30 OOD, 3 same-task replicates; nobank / orig_m / P4 arms reused from their runs; paired per-task differences with a 10k task-level bootstrap.", "",
          "## Caveats", "",
          "- Single benchmark, N = 30 train tasks, 8 zero tasks with 3 trajectories each, Qwen3-8B via API, one consumer protocol; bank-size curve on one bank; no method proposals.",
          "- The 100-config changes truncation semantics (engine done no longer coincides with the runner's 50-step stop); step-cap statistics are computed from step counts.",
          "- The RL cost table is an estimate from released hyper-parameters, not a measurement."]
    (RES / "report.md").write_text("\n".join(L) + "\n")
    print("... wrote", RES / "report.md")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "?")
