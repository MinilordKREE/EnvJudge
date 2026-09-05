"""O1-O8 statistics with 10,000-resample task-level bootstrap CIs, S1 stop rule, verdict.md.

Inputs (results/eobs/): tasks.csv, baseline_rollouts.jsonl, candidates.jsonl, certificates.jsonl,
recoverability.jsonl, ledger.jsonl. Candidate-level rates resample TASKS (all candidates of a resampled
task enter together). Bold only for the S1 outcome. No interpretation beyond PREREG §4.
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


def boot_rate(groups: dict, num, den) -> tuple[float, float, float, int, int]:
    """groups: task -> list of items. Rate = sum(num(item)) / sum(den(item)) over resampled TASKS."""
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


def status(point, lo, hi, thr, ge=True) -> str:
    if point != point:
        return "inconclusive"
    ok = point >= thr if ge else point <= thr
    decisive = (lo >= thr if ge else hi <= thr) if ok else (hi < thr if ge else lo > thr)
    return ("supported" if ok else "contradicted") + (" (CI-decisive)" if decisive else " (CI not decisive)")


def main(results: Path = RESULTS, prereg_sha: str = "", config_sha: str = "") -> None:
    tasks = list(csv.DictReader(open(results / "tasks.csv", encoding="utf-8"))) if (results / "tasks.csv").exists() else []
    cands = _jsonl(results / "candidates.jsonl")
    certs = {c["candidate_id"]: c for c in _jsonl(results / "certificates.jsonl")}
    recov = _jsonl(results / "recoverability.jsonl")
    led = ledger_totals(results / "ledger.jsonl")
    N = len(tasks)
    V: list[str] = []
    st: dict[str, str] = {}

    def out(name, text, s):
        st[name] = s
        V.append(f"### {name}: {s}\n\n{text}\n")

    def f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    # ---- O1 witness coverage
    g = {t["task_id"]: [t] for t in tasks}
    r = boot_rate(g, lambda t: t.get("W_base") in ("True", "1", True), lambda t: 1)
    out("O1 witness coverage: W_base >= 0.95", f"W_base share = {rs(r)}. Tasks without a base witness: {[t['task_id'] for t in tasks if t.get('W_base') not in ('True', '1', True)]}. Branch (§4): free-witness availability; size of the no-witness bucket.", status(r[0], r[1], r[2], 0.95))

    # ---- O2 bimodality
    r = boot_rate(g, lambda t: 0.2 <= f(t.get("p16")) <= 0.8, lambda t: f(t.get("p16")) == f(t.get("p16")))
    hist = Counter(round(f(t.get("p16")), 2) for t in tasks if f(t.get("p16")) == f(t.get("p16")))
    out("O2 bimodality: share of tasks with p16 in [0.2, 0.8] <= 0.35", f"share = {rs(r)}; p16 histogram = {dict(sorted(hist.items()))}. Branch: whether saturated/zero regimes dominate under DeepSeek.", status(r[0], r[1], r[2], 0.35, ge=False))

    # ---- O3 0/5 unreliability
    zero5 = {t["task_id"]: [t] for t in tasks if f(t.get("p5")) == 0.0}
    r = boot_rate(zero5, lambda t: f(t.get("p16")) > 0, lambda t: 1)
    out("O3 0/5 unreliability: among p5 = 0 tasks, share with p16 > 0 >= 0.20", f"share = {rs(r)}. Branch: sequential estimation vs fixed K=5.", status(r[0], r[1], r[2], 0.20))

    # ---- O4 transformation-induced zero success
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
    rc = boot_rate(cert_zero, lambda c: treated(c), lambda c: 1)
    sa, sb, sc = status(ra[0], ra[1], ra[2], 0.15), status(rb[0], rb[1], rb[2], 0.30), status(rc[0], rc[1], rc[2], 0.30)
    o4_all = all(s.startswith("supported") for s in (sa, sb, sc))
    out("O4 transformation-induced zero success (a) SR_c=0 share >= 0.15; (b) certified among them >= 0.30; (c) treated-as-unsolvable among certified >= 0.30",
        f"(a) {rs(ra)} -> {sa}\n(b) {rs(rb)} -> {sb}\n(c) {rs(rc)} -> {sc}\nBranch: whether a certification layer changes any decision.",
        "supported" if o4_all else ("inconclusive" if any(s == "inconclusive" for s in (sa, sb, sc)) else "contradicted"))

    # ---- O5 old-witness false alarm
    cert_all = {t: [c for c in cs if certs.get(c["candidate_id"], {}).get("certified")] for t, cs in validated.items()}
    at = {t: [c for c in cs if set(c.get("axes", [])) & {"A", "T"}] for t, cs in cert_all.items()}
    at = {t: cs for t, cs in at.items() if cs}
    o_only = {t: [c for c in cs if set(c.get("axes", [])) == {"O"}] for t, cs in cert_all.items()}
    o_only = {t: cs for t, cs in o_only.items() if cs}
    r_old_of = lambda c: (certs.get(c["candidate_id"], {}).get("R_old") or {}).get("ok")
    r1 = boot_rate(at, lambda c: r_old_of(c) is False, lambda c: r_old_of(c) is not None)
    r2 = boot_rate(o_only, lambda c: r_old_of(c) is True, lambda c: r_old_of(c) is not None)
    s1, s2 = status(r1[0], r1[1], r1[2], 0.30), status(r2[0], r2[1], r2[2], 0.90)
    out("O5 old-witness false alarm: certified A/T candidates with R_old = 0 >= 0.30; certified O-only with R_old = 1 >= 0.90",
        f"A/T: {rs(r1)} -> {s1}\nO-only: {rs(r2)} -> {s2}\nBranch: per-axis certificates vs single replay.",
        "supported" if s1.startswith("supported") and s2.startswith("supported") else ("inconclusive" if "inconclusive" in (s1, s2) else "contradicted"))

    # ---- O6 recoverability
    gr = defaultdict(list)
    for rr in recov:
        gr[rr["task_id"]].append(rr)
    rL = boot_rate(gr, lambda rr: rr["L"] >= 2, lambda rr: 1)
    rM = boot_rate(gr, lambda rr: rr["monotone"] == 0, lambda rr: 1)
    lt = [rr["L"] / max(rr["T_eval"], 1) for rr in recov if rr["L"] >= 0]
    lt_hist = Counter(f"{min(int(x * 10), 9) / 10:.1f}" for x in lt)
    sL, sM = status(rL[0], rL[1], rL[2], 0.50), status(rM[0], rM[1], rM[2], 0.20)
    out("O6 recoverability: L >= 2 share >= 0.50; non-monotone share >= 0.20",
        f"L>=2: {rs(rL)} -> {sL}\nnon-monotone: {rs(rM)} -> {sM}\nL/T histogram (bins of 0.1): {dict(sorted(lt_hist.items()))}; trajectories = {len(recov)}; expert_errors total = {sum(rr.get('expert_errors', 0) for rr in recov)}; recover_mode = {set(rr.get('recover_mode') for rr in recov)}.\nBranch: material for a certified self-prefix Stage; bisection admissible only if non-monotone < 0.20.",
        f"L>=2 {sL}; non-monotone {sM}")

    # ---- O7 saturated waste
    sat = {t["task_id"]: [t] for t in tasks if f(t.get("p5")) == 1.0}
    r = boot_rate(sat, lambda t: t.get("accepted") not in ("True", "1", True), lambda t: 1)
    out("O7 saturated waste: among p5 = 1 tasks, share with no ACCEPT >= 0.25", f"share = {rs(r)}. Note: the ALFWorld designer block instructs SKIP at baseline_sr >= 0.8 (skip_passthrough_candidates: true), so skipped tasks count as 'no ACCEPT'. Branch: harden branch (freeze/reallocate vs keep hardening).", status(r[0], r[1], r[2], 0.25))

    # ---- O8 descriptive
    n_val = sum(int(c.get("k") or 0) for c in cands)
    n_val_zero = sum(int(c.get("k") or 0) for c in cands if f(c.get("SR_c")) == 0.0)
    n_accept = sum(1 for c in cands if c.get("decision") == "accept")
    hint_cost = [ (certs[c]["R_hint"] or {}).get("attempts", 0) for c in certs if certs[c].get("R_hint")]
    out("O8 descriptive", f"validation rollouts on SR_c=0 candidates: {n_val_zero}/{n_val} = {fmt(n_val_zero / n_val) if n_val else 'nan'}; rollouts per ACCEPT = {fmt(n_val / n_accept) if n_accept else 'nan'} ({n_accept} accepts); R_hint attempts over {len(hint_cost)} candidates = {sum(hint_cost)}; spend by phase = { {k: round(v, 2) for k, v in led['by_phase'].items()} }.", "descriptive")

    # ---- S1
    o4_fail = st.get(next(k for k in st if k.startswith("O4")), "") == "contradicted"
    o6_L_fail = sL.startswith("contradicted")
    s1_out = "STOP the CEA line on ALFWorld" if (o4_fail and o6_L_fail) else ("proceed to method design with the branches selected above" if not any(v == "inconclusive" for v in st.values()) else "inconclusive (missing data)")

    lines = [f"# E-obs verdict — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
             f"PREREG sha `{prereg_sha}`; config sha256 `{config_sha}`; N = {N}; spend USD {led['usd']:.2f} (peak-bound {led['usd_peak_bound']:.2f}) over {led['calls']} calls; candidates = {len(cands)}; certificates = {len(certs)}; recoverability trajectories = {len(recov)}.", "",
             "## Predictions (10,000-resample task-level bootstrap 95% CIs; 'CI-decisive' = CI excludes the threshold)", ""] + V + [
             f"## S1 outcome: **{s1_out}**", "",
             "Rule: stop iff O4(a)∧(b)∧(c) all fail AND O6 (L>=2 share) fails; otherwise proceed to method design with the branches above. No GO/NO-GO on the method.", "",
             "## Descriptive tables", ""]
    # task types x regimes
    reg = defaultdict(Counter)
    for t in tasks:
        p = f(t.get("p16"))
        regime = "n/a" if p != p else ("zero" if p == 0 else ("saturated" if p == 1 else ("band" if 0.2 <= p <= 0.8 else "edge")))
        reg[t.get("type", "?")][regime] += 1
    lines += ["### Task type × regime (p16)", "", "| type | " + " | ".join(("zero", "edge", "band", "saturated", "n/a")) + " |", "|---|---|---|---|---|---|"]
    for ty, c in sorted(reg.items()):
        lines.append(f"| {ty} | " + " | ".join(str(c.get(k, 0)) for k in ("zero", "edge", "band", "saturated", "n/a")) + " |")
    ax = defaultdict(Counter)
    for c in cands:
        ce = certs.get(c["candidate_id"], {})
        key = "certified" if ce.get("certified") else ("unresolved" if ce else "no-cert")
        ax[c.get("axis", "?")][key] += 1
        ax[c.get("axis", "?")]["R_old=1"] += int(bool((ce.get("R_old") or {}).get("ok")))
        ax[c.get("axis", "?")]["R_exp=1"] += int(bool((ce.get("R_exp") or {}).get("ok")))
        ax[c.get("axis", "?")]["SR_c=0"] += int(f(c.get("SR_c")) == 0.0)
    lines += ["", "### Axis × certificate outcomes", "", "| axis | n | SR_c=0 | certified | unresolved | R_old=1 | R_exp=1 |", "|---|---|---|---|---|---|---|"]
    for a, c in sorted(ax.items()):
        n = sum(1 for x in cands if x.get("axis") == a)
        lines.append(f"| {a} | {n} | {c['SR_c=0']} | {c['certified']} | {c['unresolved']} | {c['R_old=1']} | {c['R_exp=1']} |")
    dx = Counter((c.get("decision"), "certified" if certs.get(c["candidate_id"], {}).get("certified") else "not") for c in cands)
    lines += ["", "### Decision × certified", "", f"{dict(dx)}", "", "### L/T histogram", "", f"{dict(sorted(lt_hist.items()))}", "",
              "### Cost per phase", "", f"{ {k: round(v, 2) for k, v in led['by_phase'].items()} } (USD, applicable tariff)", "",
              "## Measurement notes", "", "- Paired vs independent: p16 combines EnvRigger's own 5 baseline rollouts with 11 extra rollouts through the same code path (same PolicySpec/EpisodeSpec); candidate certificates are LLM-free replays on the same seeds.",
              "- Any post-hoc bug fix and archived pre-fix files are listed in LOG.md and named here when applicable.", "",
              "## Caveats", "", "- Single benchmark (ALFWorld train split), N tasks as set by the Phase-0 projection, DeepSeek V4 Pro (non-thinking, temperature 0.5 per config) instead of the paper's Gemini backbones, handcoded ALFWorld expert as the witness (closed-loop, stateful; recover_mode above), R_hint capped at 60 candidates × 3 attempts.",
              "- litellm moves a leading `<think>...</think>` block from `content` into `reasoning_content`; envharness stores `content` as policy_raw_response, so the designer's baseline-trajectory view carries actions and observations but not the policy's think text (substrate behaviour of the released stack with this litellm version)."]
    (results / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"... wrote {results / 'verdict.md'}")


if __name__ == "__main__":
    import sys
    main(prereg_sha=sys.argv[1] if len(sys.argv) > 1 else "", config_sha=sys.argv[2] if len(sys.argv) > 2 else "")
