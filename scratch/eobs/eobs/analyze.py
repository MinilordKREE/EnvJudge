"""O1-O8 (released arm) and O4H/O5H/O7H/O8H (hardening arm, PREREG_H) with 10,000-resample task-level bootstrap CIs,
S1 stop rule, verdict.md. Candidate-level rates resample TASKS. Bold only for the S1 outcome.

Inputs (results/eobs/): tasks.csv, candidates.jsonl (field `arm` ∈ {released, H}), certificates.jsonl,
recoverability.jsonl, witness_base.jsonl, ledger.jsonl.
S1 (owner fix 2026-09-05): O4 counts as FAILED only when (a), (b) and (c) are each contradicted.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from eobs.llm import ledger_totals
from eobs.settings import RESULTS

B = 10_000
RNG = np.random.default_rng(20260906)


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()] if Path(p).exists() else []


def fmt(x) -> str:
    return "nan" if x is None or x != x else f"{x:.3f}"


def f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def truthy(x) -> bool:
    return x in (True, "True", "true", "1", 1)


def boot_rate(groups: dict, num, den) -> tuple[float, float, float, int, int]:
    tasks = list(groups)
    if not tasks:
        return float("nan"), float("nan"), float("nan"), 0, 0
    n_t = np.array([sum(num(i) for i in groups[t]) for t in tasks], float)
    d_t = np.array([sum(den(i) for i in groups[t]) for t in tasks], float)
    if d_t.sum() == 0:
        return float("nan"), float("nan"), float("nan"), 0, len(tasks)
    point = n_t.sum() / d_t.sum()
    idx = RNG.integers(0, len(tasks), size=(B, len(tasks)))
    num_s, den_s = n_t[idx].sum(axis=1), d_t[idx].sum(axis=1)
    ok = den_s > 0
    rates = num_s[ok] / den_s[ok]
    return float(point), float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5)), int(d_t.sum()), len(tasks)


def rs(r) -> str:
    m, lo, hi, n, nt = r
    return f"{fmt(m)} [{fmt(lo)}, {fmt(hi)}] (n={n}, tasks={nt})"


def status(r, thr, ge=True) -> str:
    point, lo, hi = r[0], r[1], r[2]
    if point != point:
        return "inconclusive"
    ok = point >= thr if ge else point <= thr
    decisive = (lo >= thr if ge else hi <= thr) if ok else (hi < thr if ge else lo > thr)
    return ("supported" if ok else "contradicted") + (" (CI-decisive)" if decisive else " (CI not decisive)")


def contribution2_block(arm: str, cands: list[dict], certs: dict, tasks: list[dict], suffix: str) -> tuple[list[str], dict]:
    """O4/O5/O7 for one arm (suffix '' for released, 'H' for the hardening arm)."""
    V, st = [], {}

    def out(name, text, s):
        st[name] = s
        V.append(f"### {name}: {s}\n\n{text}\n")

    by_task = defaultdict(list)
    for c in cands:
        by_task[c["task_id"]].append(c)
    validated = {t: [c for c in cs if c.get("SR_c") is not None] for t, cs in by_task.items()}
    ra = boot_rate(validated, lambda c: f(c.get("SR_c")) == 0.0, lambda c: 1)
    zero_c = {t: [c for c in cs if f(c.get("SR_c")) == 0.0] for t, cs in validated.items()}
    zero_c = {t: cs for t, cs in zero_c.items() if cs}
    rb = boot_rate(zero_c, lambda c: bool(certs.get(c["candidate_id"], {}).get("certified")), lambda c: c["candidate_id"] in certs)
    cert_zero = {t: [c for c in cs if certs.get(c["candidate_id"], {}).get("certified")] for t, cs in zero_c.items()}
    cert_zero = {t: cs for t, cs in cert_zero.items() if cs}
    treated = lambda c: (c.get("decision") == "reject") or bool(c.get("reverse_or_loosen"))
    rc = boot_rate(cert_zero, treated, lambda c: 1)
    sa, sb, sc = status(ra, 0.15), status(rb, 0.30), status(rc, 0.30)
    subs = (sa, sb, sc)
    o4 = "supported" if all(s.startswith("supported") for s in subs) else ("inconclusive" if any(s == "inconclusive" for s in subs) else "contradicted")
    o4_all_failed = all(s.startswith("contradicted") for s in subs)
    unin = " Uninformative by construction on the released arm (scaffold-only prompt, see PREREG_H)." if suffix == "" else ""
    out(f"O4{suffix} transformation-induced zero success: (a) SR_c=0 share >= 0.15; (b) certified among them >= 0.30; (c) treated as unsolvable among certified >= 0.30",
        f"(a) {rs(ra)} -> {sa}\n(b) {rs(rb)} -> {sb}\n(c) {rs(rc)} -> {sc}\nAll three sub-items contradicted: {o4_all_failed}.{unin}\nBranch (§4): whether a certification layer changes any decision.", o4)
    cert_all = {t: [c for c in cs if certs.get(c["candidate_id"], {}).get("certified")] for t, cs in validated.items()}
    at = {t: [c for c in cs if set(c.get("axes", [])) & {"A", "T"}] for t, cs in cert_all.items()}
    at = {t: cs for t, cs in at.items() if cs}
    o_only = {t: [c for c in cs if set(c.get("axes", [])) == {"O"}] for t, cs in cert_all.items()}
    o_only = {t: cs for t, cs in o_only.items() if cs}
    r_old_of = lambda c: (certs.get(c["candidate_id"], {}).get("R_old") or {}).get("ok")
    r1 = boot_rate(at, lambda c: r_old_of(c) is False, lambda c: r_old_of(c) is not None)
    r2 = boot_rate(o_only, lambda c: r_old_of(c) is True, lambda c: r_old_of(c) is not None)
    s1, s2 = status(r1, 0.30), status(r2, 0.90)
    out(f"O5{suffix} old-witness false alarm: certified A/T candidates with R_old = 0 >= 0.30; certified O-only with R_old = 1 >= 0.90",
        f"A/T: {rs(r1)} -> {s1}\nO-only: {rs(r2)} -> {s2}{unin}\nBranch: per-axis certificates vs single replay.",
        "supported" if s1.startswith("supported") and s2.startswith("supported") else ("inconclusive" if "inconclusive" in (s1, s2) else "contradicted"))
    sat = {t["task_id"]: [t] for t in tasks if f(t.get("p5" + ("_H" if suffix else ""))) == 1.0}
    acc_key = "accepted" + ("_H" if suffix else "")
    r7 = boot_rate(sat, lambda t: not truthy(t.get(acc_key)), lambda t: 1)
    note7 = (" On the released arm the ALFWorld designer block instructs SKIP at baseline_sr >= 0.8 (skip_passthrough_candidates: true), so 'no ACCEPT' holds by construction: UNINFORMATIVE." if suffix == "" else "")
    out(f"O7{suffix} saturated waste: among p5 = 1 tasks, share with no ACCEPT >= 0.25", f"share = {rs(r7)}.{note7} Branch: harden branch (freeze/reallocate vs keep hardening).", status(r7, 0.25))
    n_val = sum(int(c.get("k") or 0) for c in cands)
    n_val_zero = sum(int(c.get("k") or 0) for c in cands if f(c.get("SR_c")) == 0.0)
    n_accept = sum(1 for c in cands if c.get("decision") == "accept")
    hint = [(certs[c["candidate_id"]].get("R_hint") or {}) for c in cands if certs.get(c["candidate_id"], {}).get("R_hint")]
    hint_cert = [h for h in hint if h.get("ok")]
    out(f"O8{suffix} descriptive", f"validation rollouts on SR_c=0 candidates: {n_val_zero}/{n_val} = {fmt(n_val_zero / n_val) if n_val else 'nan'}; rollouts per ACCEPT = {fmt(n_val / n_accept) if n_accept else 'nan'} ({n_accept} accepts over {len(cands)} validated candidates); R_hint attempts {sum(h.get('attempts', 0) for h in hint)} over {len(hint)} candidates, {len(hint_cert)} certified by hint ({fmt(sum(h.get('attempts', 0) for h in hint) / len(hint_cert)) if hint_cert else 'nan'} attempts per hint-certified candidate).", "descriptive")
    st["_o4_all_failed"] = o4_all_failed
    return V, st


def main(results: Path = RESULTS, prereg_sha: str = "", config_sha: str = "", prereg_h_sha: str = "", config_h_sha: str = "") -> None:
    tasks = list(csv.DictReader(open(results / "tasks.csv", encoding="utf-8"))) if (results / "tasks.csv").exists() else []
    cands_all = _jsonl(results / "candidates.jsonl")
    certs = {c["candidate_id"]: c for c in _jsonl(results / "certificates.jsonl")}
    recov = _jsonl(results / "recoverability.jsonl")
    witness = _jsonl(results / "witness_base.jsonl")
    led = ledger_totals(results / "ledger.jsonl")
    N = len(tasks)
    V: list[str] = []
    st: dict[str, str] = {}

    def out(name, text, s):
        st[name] = s
        V.append(f"### {name}: {s}\n\n{text}\n")

    g = {t["task_id"]: [t] for t in tasks}
    r = boot_rate(g, lambda t: truthy(t.get("W_base")), lambda t: 1)
    r50 = boot_rate(g, lambda t: truthy(t.get("within_policy_cap")), lambda t: 1)
    wreasons = Counter(w.get("reason") for w in witness if not w.get("W_base"))
    out("O1 witness coverage: W_base >= 0.95", f"W_base (expert from reset, cap 150 steps) = {rs(r)}; W_base within the policy cap of 50 steps = {rs(r50)}. Expert-failure reasons on non-witnessed tasks (expert calibration from reset): {dict(wreasons)}; tasks: {[t['task_id'] for t in tasks if not truthy(t.get('W_base'))]}. Branch: free-witness availability; size of the no-witness bucket.", status(r, 0.95))

    r = boot_rate(g, lambda t: 0.2 <= f(t.get("p16")) <= 0.8, lambda t: f(t.get("p16")) == f(t.get("p16")))
    hist = Counter(round(f(t.get("p16")), 2) for t in tasks if f(t.get("p16")) == f(t.get("p16")))
    out("O2 bimodality: share of tasks with p16 in [0.2, 0.8] <= 0.35", f"share = {rs(r)}; p16 histogram = {dict(sorted(hist.items()))}. Branch: whether saturated/zero regimes dominate under DeepSeek.", status(r, 0.35, ge=False))

    zero5 = {t["task_id"]: [t] for t in tasks if f(t.get("p5")) == 0.0}
    r = boot_rate(zero5, lambda t: f(t.get("p16")) > 0, lambda t: 1)
    out("O3 0/5 unreliability: among p5 = 0 tasks, share with p16 > 0 >= 0.20", f"share = {rs(r)} (p5 = 0 tasks: {list(zero5)}). Branch: sequential estimation vs fixed K=5.", status(r, 0.20))

    released = [c for c in cands_all if c.get("arm", "released") == "released"]
    hard = [c for c in cands_all if c.get("arm") == "H"]
    V2, st2 = contribution2_block("released", released, certs, tasks, "")
    V += V2
    st.update({k: v for k, v in st2.items() if not k.startswith("_")})

    gr = defaultdict(list)
    for rr in recov:
        gr[rr["task_id"]].append(rr)
    rL = boot_rate(gr, lambda rr: rr["L"] >= 2, lambda rr: 1)
    rM = boot_rate(gr, lambda rr: rr["monotone"] == 0, lambda rr: 1)
    rLx = boot_rate(gr, lambda rr: (rr.get("excluded") or {}).get("L", -1) >= 2, lambda rr: 1)
    rMx = boot_rate(gr, lambda rr: (rr.get("excluded") or {}).get("monotone", 1) == 0, lambda rr: 1)
    lt = [rr["L"] / max(rr["T_eval"], 1) for rr in recov if rr["L"] >= 0]
    lt_hist = Counter(f"{min(int(x * 10), 9) / 10:.1f}" for x in lt)
    sL, sM = status(rL, 0.50), status(rM, 0.20)
    ef = Counter(x for rr in recov for x in rr.get("reasons", []) if x in ("expert_error", "expert_stuck", "expert_timeout"))
    out("O6 recoverability: L >= 2 share >= 0.50; non-monotone share >= 0.20",
        f"CONSERVATIVE (expert failure counts C=0): L>=2 {rs(rL)} -> {sL}; non-monotone {rs(rM)} -> {sM}.\nEXCLUDED (expert-failure prefixes dropped): L>=2 {rs(rLx)} -> {status(rLx, 0.50)}; non-monotone {rs(rMx)} -> {status(rMx, 0.20)}.\nL/T histogram (bins of 0.1, conservative): {dict(sorted(lt_hist.items()))}; trajectories = {len(recov)}; prefixes evaluated = {sum(rr.get('T_eval', 0) + 1 for rr in recov)}; expert failures by class = {dict(ef)}; recover_mode = {sorted(set(rr.get('recover_mode') for rr in recov))}.\nBranch: material for a certified self-prefix Stage; bisection admissible only if non-monotone < 0.20.",
        f"L>=2 {sL}; non-monotone {sM}")

    VH, stH = ([], {})
    if hard:
        VH, stH = contribution2_block("H", hard, certs, tasks, "H")
        st.update({k: v for k, v in stH.items() if not k.startswith("_")})

    o4_all_failed = st2.get("_o4_all_failed", False)
    o6_L_fail = sL.startswith("contradicted")
    if any(v == "inconclusive" for k, v in st.items() if k.startswith(("O1", "O2", "O3", "O4 ", "O6"))):
        s1_out = "inconclusive (missing data)"
    elif o4_all_failed and o6_L_fail:
        s1_out = "STOP the CEA line on ALFWorld"
    else:
        s1_out = "proceed to method design with the branches selected above"

    lines = [f"# E-obs verdict — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
             f"PREREG sha `{prereg_sha}`; config sha256 `{config_sha}`; PREREG_H sha `{prereg_h_sha}`; H config sha256 `{config_h_sha}`; N = {N}; spend USD {led['usd']:.2f} (peak-bound {led['usd_peak_bound']:.2f}) over {led['calls']} calls; candidates released/H = {len(released)}/{len(hard)}; certificates = {len(certs)}; recoverability trajectories = {len(recov)}.", "",
             "## Predictions, released arm (10,000-resample task-level bootstrap 95% CIs; 'CI-decisive' = CI excludes the threshold)", ""] + V
    if VH:
        lines += ["## Predictions, hardening arm (PREREG_H: App. G configuration)", ""] + VH
    lines += [f"## S1 outcome: **{s1_out}**", "",
              "Rule (PREREG §4, evaluated on the released arm): stop iff O4(a)∧(b)∧(c) are ALL contradicted AND O6 (L>=2 share) is contradicted; otherwise proceed to method design with the branches above. No GO/NO-GO on the method.", "",
              "## Descriptive tables", ""]
    reg = defaultdict(Counter)
    for t in tasks:
        p = f(t.get("p16"))
        regime = "n/a" if p != p else ("zero" if p == 0 else ("saturated" if p == 1 else ("band" if 0.2 <= p <= 0.8 else "edge")))
        reg[t.get("type", "?")][regime] += 1
    lines += ["### Task type × regime (p16)", "", "| type | zero | edge | band | saturated | n/a |", "|---|---|---|---|---|---|"]
    for ty, c in sorted(reg.items()):
        lines.append(f"| {ty} | " + " | ".join(str(c.get(k, 0)) for k in ("zero", "edge", "band", "saturated", "n/a")) + " |")
    for arm_name, cs in (("released", released), ("H", hard)):
        if not cs:
            continue
        ax = defaultdict(Counter)
        for c in cs:
            ce = certs.get(c["candidate_id"], {})
            a = c.get("axis", "?")
            ax[a]["n"] += 1
            ax[a]["SR_c=0"] += int(f(c.get("SR_c")) == 0.0)
            ax[a]["certified"] += int(bool(ce.get("certified")))
            ax[a]["unresolved"] += int(bool(ce) and not ce.get("certified"))
            ax[a]["R_old=1"] += int(bool((ce.get("R_old") or {}).get("ok")))
            ax[a]["R_exp=1"] += int(bool((ce.get("R_exp") or {}).get("ok")))
        lines += ["", f"### Axis × certificate outcomes ({arm_name} arm)", "", "| axis | n | SR_c=0 | certified | unresolved | R_old=1 | R_exp=1 |", "|---|---|---|---|---|---|---|"]
        for a, c in sorted(ax.items()):
            lines.append(f"| {a} | {c['n']} | {c['SR_c=0']} | {c['certified']} | {c['unresolved']} | {c['R_old=1']} | {c['R_exp=1']} |")
        dx = Counter((c.get("decision"), "certified" if certs.get(c["candidate_id"], {}).get("certified") else "not") for c in cs)
        lines += ["", f"### Decision × certified ({arm_name} arm)", "", f"{dict(dx)}"]
        snippets = [(c["task_id"], c["candidate_id"], c.get("decision"), c.get("matched_snippet")) for c in cs if c.get("reverse_or_loosen")]
        lines += ["", f"### reverse_or_loosen matches for audit ({arm_name} arm; {len(snippets)} candidates)", ""] + [f"- task {t} cand {cid} [{d}]: {s}" for t, cid, d, s in snippets]
        al = Counter()
        for c in cs:
            al[("propose", c.get("propose_align"))] += 1
            al[("decide", c.get("decision_text_source"))] += 1
        lines += ["", f"### Designer-call alignment ({arm_name} arm): {dict(al)}"]
    lines += ["", "### L/T histogram", "", f"{dict(sorted(lt_hist.items()))}", "", "### Cost per phase (USD, applicable tariff)", "", f"{ {k: round(v, 2) for k, v in led['by_phase'].items()} }", "",
              "## Measurement notes", "",
              "- Paired vs independent: p16 = EnvRigger's own 5 baseline rollouts + 11 extra rollouts through the same code path (system prompt and first observation byte-identical, checked on tasks 0 and 1); candidate certificates are LLM-free replays on the same seeds; the two designer arms are independent runs on the same seeds.",
              "- Expert = ALFWorld handcoded expert, closed-loop and stateful (recover_mode handcoded_closed_loop); its own failure rate from reset is the O1 calibration; O6 is reported with expert failures counted as C=0 (conservative) and excluded.",
              "- Bug fixes after rollouts and archived pre-fix files are listed in LOG.md and named here when applicable: witness_base_v1_prestuckclass.jsonl (witness classification before expert_stuck/expert_timeout were separated; W_base values unchanged).", "",
              "## Caveats", "",
              "- Single benchmark (ALFWorld train split), N per the Phase-0 projection, DeepSeek V4 Pro non-thinking at temperature 0.5 (config) instead of the paper's Gemini backbones, handcoded expert as witness (fails on some pick_two tasks), R_hint capped at 60 candidates × 3 attempts shared across arms.",
              "- Released-arm O4/O5/O7 are uninformative by construction (scaffold-only ALFWorld prompt: SKIP at SR >= 0.8, A/O blocking forbidden, acceptance = SR gain >= 0.2); contribution-2 branches are read from the H arm (PREREG_H).",
              "- litellm 1.99.0 moves a leading <think> block into reasoning_content; policy_raw_response therefore lacks think text (substrate behaviour of the released stack)."]
    (results / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"... wrote {results / 'verdict.md'}")


if __name__ == "__main__":
    import sys
    a = sys.argv[1:] + [""] * 4
    main(prereg_sha=a[0], config_sha=a[1], prereg_h_sha=a[2], config_h_sha=a[3])
