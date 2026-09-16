# Privilege evidence verification: round 1 stopped

**Outcome: IMPLEMENTATION_FAILURE; Phase A did not pass.** Implementation and validation
preregistration commit: `17f420c2fdd3a9ecb8dfb15481054813937ea3b8`. This round stopped after
19 of 21 scheduled cases. No saved full admission replay, designer call, learner rollout,
or Phase B task154/159 engineering run was dispatched.

## Recorded results

All 13 labeled core cases completed, with 4/13 expected verdicts: 1/9 leak cases returned
FAIL and 3/4 legitimate cases returned PASS. Seven leak cases returned UNCERTAIN; one
filtering leak incorrectly returned PASS. Repeat agreement was 2/4. Two of four unlabeled
saved inspections completed, both UNCERTAIN; the remaining two were not dispatched.
These are engineering diagnostics on reused cases, not a generalization estimate.

The 19 completed records contain 13 generated uncertainties. Offline review attributes
them to seven out-of-range runtime coordinates, two incorrect group/reference bindings,
two incompatible public citation bases, one unresolved narrower proposition after the
bounded reconsideration, and one internal schema violation. All 26 parsed source anchors
matched exactly. Of 45 runtime anchors, 27 matched; 14 of the 18 incorrect anchors confused
an activation-table identifier with a position in the groups array.

The filtering false negative was semantic: the checker treated a hardcoded selection
criterion as generic because the selected option was already visible. Public availability
of an option does not establish authorization for the criterion selecting it. The generic
prerequisite case also retained a false-positive interpretation, independently of its
invalid final public citation. These findings do not justify weakening admission.

## Implementation interruption and audit

The second completed saved inspection returned 11 candidate anchors against the frozen
maximum of eight. It correctly became UNCERTAIN. However, the error string embedded a
Pydantic input-value representation whose dictionary ordering changed after sorted JSON
journaling. Offline replay reproduced every request, response and verdict, but three
copies of that generated uncertainty text differed. The exact-record audit stopped the
run. Eighteen final records replay exactly; the remaining difference is confined to
those three error-text fields.

The independent audit retains `integrity: FAIL` and `judge_ready: false`. Its accounting
checks pass. Four failed checks remain visible: incomplete 21-case schedule, recorded
interruption, the nineteenth exact-final-record comparison, and the initial auditor's
omission of the outer implementation-failure precedence. A separate check confirms the
recorded implementation-failure precedence. No original result, error, journal, or cap
has been rewritten, relabeled, resumed, or forgiven.

## Accounting and privacy

There were 42 logical requests/responses and 43 physical attempts: 42 returned and one
ambiguous attempt whose entire reservation remains charged. No reservation is in flight.

| Conservative accounting | USD |
| --- | ---: |
| This round: returned usage | 0.58990976 |
| This round: retained ambiguous reservation | 0.46601632 |
| This round: total | 1.05592608 |
| Four previous validations | 1.44588620 |
| Cumulative experiment | 2.50181228 |
| Remaining under the authorized USD20 ceiling | 17.49818772 |

Before this round, 915 unit tests and 10 LLM-free integration tests passed (one integration
skip); repository hooks, Ruff and strict mypy passed. The original LOW common driver,
model/settings, public PrivilegeDecision schema and underlying case inputs were unchanged.

Public artifacts contain only code, synthetic tests, enums, counts and hashes. Complete
references, GT-derived observations/actions, all prompts, candidate effects and decision
prose remain local and gitignored. The implementation publication audit checked 501
fingerprints and three reference structures with zero findings. Previous research records
remain unchanged.

## Next-round boundary

The preregistered operational stop occurred and remains recorded here. The user's explicit
instruction allows unsuccessful rounds to be followed by another round, up to five. Any
continuation will therefore be a separately frozen round 2 after offline repair and audit,
with an explicit narrow continuation amendment and all prior costs carried forward.
It must start the same complete 21-case schedule in a new namespace. This report does not
admit a candidate or authorize Phase B before a new Phase A passes.

Artifacts: `frozen/iterative_low_llm_judge_evidence/round-1/validation_result.json` and
`frozen/iterative_low_llm_judge_evidence/round-1/independent_audit.json`.
