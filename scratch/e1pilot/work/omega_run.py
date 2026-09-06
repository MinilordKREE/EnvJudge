import json, csv, sys, pathlib
sys.path.insert(0, "/home/kree/work/EnvJudge/scratch/eobs"); sys.path.insert(0, "/home/kree/work/EnvJudge/scratch/e1pilot"); sys.path.insert(0, "/home/kree/work/EnvJudge/scratch/e1pilot/p4")
from p4.omega import omega, candidate_from_row
E = pathlib.Path("/home/kree/work/EnvJudge/scratch/e1pilot")
rows = [json.loads(l) for l in open(E / "results/e1pilot/p2b_doses.jsonl")]
hits = {}
for r in rows:
    if r.get("class") == "IN-BAND" and r["task_id"] not in hits: hits[r["task_id"]] = r
out = []
for tid, r in sorted(hits.items()):
    w, ok, n = omega(tid, candidate_from_row(r))
    out.append({"task_id": tid, "env": f"{r['family']}:{r['dose']}", "omega": w, "survived": ok, "n_witnesses": n, "p8_p2b": r["p_hat"]}); print(out[-1], flush=True)
with open(E / "p4/results/omega.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print("omega written", flush=True)
