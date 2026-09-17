# Complete AEA integration

Implementation selector: `llm_v2_integrated`. Historical selectors and result files retain
their original behavior. This integrates existing components; it introduces no designer,
judge, prompt, acceptance rule or intervention family research.

## Measurement and routing

Measure the original environment afresh using the validated v0.2 estimator: Beta(1+s,1+f),
LOW below .2, MID [.2,.8], HIGH above .8; first batch 4 then batches of 2. Stop at posterior
confidence .9 or 16 valid episodes. Choose the regime with greatest posterior probability;
report s/n separately. Directly thresholding s/n would change the method at some boundaries.

E5's midpoint decision applies to CONTROL. No previous task's leverage or frontier changes
family order or the initial dose. The first interior dose is always .5, with at most four
bisections. Legacy v0.4 warm-start behavior remains reproducible under its original selector.

## Branches and freeze

- **LOW:** fresh failed baseline episodes and a lazily obtained, verified rich reference;
  iterative designer, structural/schema/API and lexical checks, frozen R5 witness-checking
  LLM privilege screen, solvability, d=1 endpoint, semantic-family freeze, dose CONTROL.
  The validated pilot's three-call limit is an instance setting, not a global monkeypatch.
  Typed `REPAIR_CODE` / `REPLACE_MECHANISM` feedback and actual parent failures are unchanged.
  FAIL and UNCERTAIN block solvability and learner evaluation, with existing bounded redesign.
- **MID:** return the original environment. No designer, reference provider or privilege judge.
- **HIGH:** one existing LLM call receives baseline success/failure evidence and proposes at
  most two `harder_with_d` Rules families. Retain validation, solvability and d=1 endpoint.
  A non-viable family may yield to the next proposal. Once a family is viable, its semantics
  freeze; CONTROL exhaustion or infeasibility ends the task without switching families.

At every measured dose the source is fixed. Existing endpoint semantics are unchanged:
0/4 and 4/4 stop immediately; mixed batches top up to 8; search accepts exactly 3–5/8.
LOW screens the reachable dose grid before any policy probe. The final LOW source and dose
must match the stored R5 PASS. Solvability uses the existing d=1 guard; this is not a new
proof for all doses or all possible states.

The frozen judge is independent semantic screening, not guaranteed information isolation.
Its previous Phase A remains NOT_READY (known generic-prerequisite false rejection).
The prospective LOW engineering pilot succeeded under this judge. This integration does
not relabel validation cases or change judge model, prompts, schemas, input, or witnesses.

## Explicit resource accounting

Each task has a fresh baseline budget of at most 16 valid policy episodes and a separate
30-episode adaptation budget. This preserves the successful LOW pilot's adaptation envelope
when replacing its archived baseline with live regime measurement. Both baseline and
adaptation count in total charged search cost, including the productivity denominator.
Endpoint reserve remains 16; candidate and bisection bounds remain enforced.

This is **not** the old E3 matched-30-total-rollout condition. The new arm can use up to 46
search episodes per task; compare raw coverage and productivity with that difference stated.
K16 is separate evaluation, never feedback. Errored episodes, physical API attempts,
returned-cost estimates and ambiguous-attempt reservations are recorded separately.

## Runtime and audit

One private directory per task stores regime/posterior evidence, designer requests and
responses, candidate lineage, exact privilege inputs/decisions, solvability, endpoints,
freeze and CONTROL, final corpus entry, search and confirmation traces, and USD accounting.
The runtime reuses the existing policy runner, horizon and public prompt. In-process
simulator replay is locked; at most 4 tasks × 4 subprocess episodes run concurrently.

The E3 launcher refuses to implicitly restart a partially executed task. A method-state hash
binds all decision artifacts before and after K16. Raw privileged references, generated code,
prompts, responses and runtime surfaces remain under gitignored `runs/`. Public artifacts
are reconstructed from a strict allowlist of task IDs, labels, counts, numeric results and
hashes. Synthetic tests cover boundaries without exposing real solutions.
