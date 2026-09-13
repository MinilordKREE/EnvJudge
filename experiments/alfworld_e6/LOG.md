# E6 LOG (UTC)

- 2026-09-13T18:35:46Z Phase 3 (smoke) started on branch aea-llm-vnext, method frozen at 47a0091; main worktree
  (E5) untouched. Frozen shared K16 summaries copied into frozen/ (sha256 0a95bc61d6932043,
  da42c9269b90ff62). Selection rule applied: HIGH 1, 7, 12; LOW 8, 9, 10. PREREG_SMOKE.md,
  scripts/e6_smoke.py, scripts/make_tables_e6_smoke.py and tests/unit/test_e6_smoke_driver.py
  written; 137 unit tests pass; no paid call made yet.
- 2026-09-13T18:36:17Z PREREG_SMOKE.md committed as dd0d914; SHA recorded in scripts/e6_smoke.py; the committed frozen copies carry one trailing newline added by the end-of-file hook (their sha256 noted in the prereg beside the source sha256). Still no paid call.
- 2026-09-13T18:36:50Z Endpoint probe OK (Alibaba). Chain launched: runs/e6_chain.sh (search -> confirm -> tables), log runs/r1-logs/e6_chain.log; experiment commit d3a90dc.
- 2026-09-13T18:36:50Z Search launched (chain runs/e6_chain.sh; manifest prereg_sha dd0d914, method_sha 47a0091, src/aea tree unmarked; git d3a90dc, tree dirty only by this LOG). Tasks in order 1, 7, 12, 8, 9, 10; every task reached its frozen regime prospectively (10/10, 10/10, 10/10, 0/10, 0/10, 0/10).
- 2026-09-13T20:02:53Z Search, confirm (0 accepted environments, nothing to confirm) and tables done. Spend USD 4.32 of 30 (search 4.29, designer 0.03). Gates: 10 of 11 pass; gate 8 (reference leakage audit) false on task 9: the recomputed expert reference hash differs from the kept one; leaks [] on every task.
- 2026-09-13T20:06:26Z Read-only diagnosis (scratch, in-process, no API call): the ALFWorld handcoded expert returns different valid solutions across sessions in one process (task 9: alarmclock 2 vs alarmclock 1); the audit recomputed in the long-lived search process and hit the other variant. Decision per PREREG_SMOKE as written: NO-GO (correctness gate failed); HIGH PASS (3/3 valid, 1/3 leverage: task 12 distractor_alarmclocks 0/4 at d=1, bracket exhausted at [0.3125, 0.375], cap); LOW PASS (3/3 grounded, task 9 unlocked 7/8 and 4/4, both too_easy). No repair, no re-run. Narrative and implementation issues in results/e6_smoke_narrative.md (appended to e6_smoke.md by the tables script); small artifacts archived under results/e6_smoke/ (traces.jsonl 15 MB not archived).
