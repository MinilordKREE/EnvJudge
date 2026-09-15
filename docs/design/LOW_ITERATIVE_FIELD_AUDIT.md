# LOW iterative field audit

Research cutoff: **2026-09-15**. Repository inspected: `aea-llm-vnext`,
`01654104c1fbf4e169280ca45bf1e5c91d0c8148`. Analysis only; no experiments.

## 1. Scope and reading protocol

The repository was reconstructed before selecting architectures. The immediate question is
whether feedback can improve a task-local environment for a **fixed learner**, within a
finite budget. Improvements to the learner, optimizer, simulator, and task distribution are
different interventions. None is evidence that iterative LOW Rules will work.

Primary arXiv HTML, methods, algorithms and appendices were used. Required IDs were checked
against their actual titles; VeriEnv's title is *Safe and Scalable Web Agent Learning via
Recreated Websites*. Searches also covered environment refinement/evolution, curriculum
co-evolution, program evolution, verifier-guided repair and harness optimization in 2025–2026.
Citation following added DGM, AlphaEvolve, GEPA and Environment Evolution for Terminal Agents.
Older mechanisms such as EnvGen, POET and Self-Refine were encountered through citations;
they are historical context, not additional experimentally reviewed methods here.

**Evidence labels:** **P** = described procedure; **E** = evaluated implementation;
**F** = proposed future loop; **NR** = not specified in the inspected source, not proof of
absence; **NA** = does not apply to that optimization object. Paper claims are distinguished
from our transfer hypotheses. Source sections accompany compact loop records. No quoted
performance result should be read as a matched comparison against AEA.

For every card, the fields cover: artifact/state; proposer/evidence; evaluator; syntax and
semantic failure; no gain/regression/partial progress; same-candidate repair versus replacement;
memory/commit/rollback; population; stopping/budget; learner/environment changes. Unmentioned
failure handlers are **NR**, not silently filled in from other methods.

## 2. Directly relevant artifact and environment loops

### EH — EnvHarness / EnvRigger [P,E]

[Primary: §3.2, Appendix E.3](https://arxiv.org/html/2608.19880v1#S3.SS2).
Object: wrapper components; state: accepted stack and current candidate. The designer reads
baseline trajectories, diagnosis, then fresh validation trajectories, success/failure/timeout
statistics and scaling feedback. It emits a component set, judged as a whole. Validation
accepts useful signals, rejects unsolvable/nonchallenging candidates, or returns a poorly scaled
candidate to Write. Same-candidate revision and replacement are permitted; no strict monotone
improvement gate or explicit rejected-candidate archive is specified. Syntax-specific repair,
regression replay and best-snapshot rollback: NR. Accepted components join the stack. Budget:
5 baseline rollouts, 5 per candidate, at most 5 write–validate rounds; component count uncapped.
Policy fixed inside customization; learning can occur between customization rounds. Loop:
environment refinement, extensible to co-evolution.

**AEA inference:** return behavioral evidence to DESIGN, while making acceptance and the
budget explicit. An EnvHarness-inspired comparison should use Rules-only candidates and the
same evaluator; a native reproduction has a broader intervention space and different gating.

### HE — HarnessEvolve [P,E]

[Primary: §§3–4, Algorithm 2](https://arxiv.org/html/2609.00829v1#S3).
Object: agent harness; state: current harness, verified references, two-batch replay buffer,
accepted snapshots. Optimizer reads failed/reference diagnoses grouped by cause. Quality gate
returns rejection reasons for up to 3 revisions; performance rejection retains the incumbent,
without an explicit same-batch performance-repair loop. Syntax handler and persistent rejected
edit buffer: NR. Algorithm accepts batch gain ≥δ and replay loss ≤ε; experimental δ=0,
ε=.025, so ties can pass. Epoch validation selects the best snapshot. Budgets: references ≤ 5
attempts/task, batch 40, epochs ≤20, batch/epoch patience10/5. One current lineage plus snapshots;
frozen backbone and environment, evolving harness. Leakage score **above** .8 is rejected;
injected-example cap 5. Loop: gated artifact optimization.

**AEA inference:** preserve a tested incumbent, feed back precise rejection causes and separate
candidate selection from independent confirmation. Cross-task clustering and an LLM leakage
judge are unnecessary for the immediate task-local design.

### SO — SkillOpt [P,E]

[Primary: Method, Algorithm 1, Appendix C](https://arxiv.org/html/2605.23904v2).
Object: skill document. State: incumbent/best, score hashes, epoch-local rejected edits,
optimizer meta guidance. Separate optimizer analyzes scored successful/failed rollouts,
merges/ranks localized add/delete/replace edits; rewrite mode also exists. Patch safeguards
skip incompatible edits; executable-code syntax/solvability checks: NA. Held-out selection
requires strict improvement: ties, regressions and unhelpful partial edits are rejected,
incumbent retained, edits/failures buffered. Accepted artifacts persist; epoch slow updates
are also gated. Default: 4 epochs, rollout batch 40, reflection batch 8, edit budget4 decaying
to 2; score cache avoids duplicate selection evaluation. Single incumbent, not a population.
Learner weights/harness and environment fixed. Loop: bounded artifact optimization with
slower optimizer memory.

**AEA inference:** Rules can be persistent optimization artifacts. A text edit count does not
bound a code patch's semantic effect. AEA also needs an objective different from maximizing
success: assistance that makes every episode trivial is not a calibrated environment.

### RS — Rethinking Self-Evolving Agent Skills [P,E]

[Primary: Framework, Experiments, Appendix A 2](https://arxiv.org/html/2608.02636v1).
Object: skill; proposer uses the fixed executor model and Normal/Fail-only/Success-only
trajectory feedback. Validation advances nondecreasing candidates; a separate best checkpoint
requires strict improvement and changed bytes. Regressions retain the incumbent. Across rounds,
only incumbent skill reaches the next proposer: earlier trajectories/rejected candidates do
not. Same artifact is revised; no population. Syntax/semantic repair taxonomy: NR. Stops:
10 rounds, 5 consecutive regressions/no-ops, or empty feedback. Backbone, harness and tasks'
environments fixed. Of 388 candidates, 55 create byte-distinct validation bests; all 11 evolved
selections in the primary study include failure feedback. Selection can disagree with test
performance. Loop: sparse validation-filtered search.

**AEA inference:** neither repeated editing nor best-so-far storage guarantees improvement.
Do not demand a success-rate increase after every proposal; do preserve failed-attempt evidence
as a separately testable addition. Its benefit is not established by this study's protocol.

### RE — Rethinking the Evaluation of Harness Evolution for Agents [P,E]

[Primary: §§3–5](https://arxiv.org/html/2607.12227v1#S3).
Compares independent trajectory sampling, sequential trajectory refinement, shared harness
evolution and task-specific harness scaling under matched feedback and inference budgets.
State differs: previous response versus persistent harness. Outcome verifiers score executions;
iteration is not itself evidence of reusable improvement. Held-out task transfer separates
reusable harness learning from discovery on evaluation tasks. This is an evaluation framework,
not one prescribed repair/rollback/population algorithm; those fields are method-specific.
Loop budgets are explicit K, not a universal recommended round count. Backbone fixed;
environment evolution is not the intervention.

**AEA inference:** compare feedback-conditioned redesign to independent family search at the
same candidate, optimizer and rollout caps. Fresh episodes of the same task establish repeat
delivery, not transfer to unseen tasks or learner improvement.

### DG — Darwin Gödel Machine [P,E]

[Primary: §§3–4, Appendix C](https://arxiv.org/html/2505.22954v3#S3).
Object: coding agent's source. A selected parent reads its benchmark logs, proposes and
implements a self-modification, then tests the child. Persistent archive contains functional
agents and their scores/lineage; lower-scoring agents can remain stepping stones. Compilation
or loss of code-editing ability prevents admission. Other semantic defects receive benchmark
feedback; no-gain/regression does not imply deleting a functional lineage. Parent retention
provides recovery; invalid-child repair details are not a general typed protocol. Selection
balances score and underexplored parents. Experiments run 80 new-agent iterations. Backbones
and archive-selection algorithm fixed; child agent code can improve subsequent self-editing.
Environment fixed. Loop: evolutionary self-modification, not environment co-evolution.

**AEA inference:** functional candidates need not be immediate winners. An80-child archive
does not justify introducing a population under AEA's20-rollout adaptation allowance.

### AE — AlphaEvolve [P,E]

[Primary: §§2.1–2.6](https://arxiv.org/html/2506.13131v1#S2).
Object: marked program regions. LLMs see sampled prior programs, outputs/scores and context,
produce diffs or rewrites, then automatic evaluators score children. Cheap-to-expensive
evaluation cascades remove faulty/unpromising programs. Database combines quality and diversity
using island/MAP-Elites-inspired selection; several ancestors inform proposals. Promising
programs persist; no-gain children need not replace any parent. Explicit universal compiler
repair, rejected-edit memory and transactional rollback: NR. Budgets/stopping are
application-specific computation limits, not a common iteration count. Optimizer models
fixed during a search; environment and learner training are not its standard inner loop.
Loop: program evolution, optionally prompt evolution.

**AEA inference:** use cheap validity checks before expensive learner probes. Do not import a
generic scalar fitness or assume noisy4/8 episode measurements resemble deterministic
mathematical evaluators.

## 3. Co-evolution, curriculum and environment-generation records

### 1. HELIX — 2608.13951v1 (2026-08-14)

**State/object:** typed harness recipes, source atoms, lockfiles; frozen model. **Proposal:** enumerated source combinations and deterministic smoke screening, not a demonstrated adaptive LLM repair search. **Verifier:** composition/conformance/boundary/purity checks; trace-strict execution, then official SWE evaluator. **Failures:** invalid compositions screened; resolved/regression/near-miss/no-action/policy/noise labels retained as matched sibling evidence; no explicit candidate-repair/rollback policy. **Memory:** traces, patches, tests, provenance and sibling dataset. **Budget:** one round, 65 candidates ×100 tasks=6,500 slots; selected follow-ups 3,000 LCB and 550 SWE slots. **Outcome:** best fixed52/100 versus 50; union79/100 is post-hoc oracle coverage. **Outer loop:** build–update–rebuild proposed, but §9.5 explicitly says no updated model was trained. Thus not demonstrated multi-round co-evolution. Transfer: candidate identity and failures-as-evidence; no support for LOW retry efficacy.

[Primary: §§3.3–3.5, 5.2–5.4, 6, 9.5](https://arxiv.org/html/2608.13951v1). Paper-linked code, not inspected: [HKUDS/HELIX](https://github.com/HKUDS/HELIX).

### 2. MetaSkill-Evolve — 2607.05297v1 (2026-07-06)

**State:** branch task skill, five meta-skill files, history in SQLite DAG. **Proposal:** worst training failure → Analyzer → tag-matched retrieval → adaptive Allocator → Proposer → Evolver. **Verify:** file hash detects no-op; validation accuracy delta scores edits; hidden test separate. **Failure/selection:** neutral/regressing children stored and retrievable but excluded as parents; only positive-gain children archived. Stagnation widens children; frontier combines utility, descendant productivity and under-selection. **Repair:** child edits recorded parent, restoring snapshots before each child; meta rewrites accumulate sequentially. Syntax/semantic-specific repair NR. **Memory:** immutable nodes, lineage/inspiration edges, task/meta snapshots; restore provides branch isolation, not automatic performance rollback. **Budget:** five fast iterations, H=2, two meta-updates; children 1–3(initial 2), frontier 3; stop all-passed or five stagnant iterations. Frozen backbone. **Caveat:** single-level baseline also disables sharing and limits children, complicating attribution solely to meta-evolution.

[Primary: §§3.2–3.5, 4.1, Appendix C](https://arxiv.org/html/2607.05297v1).

### 3. SEAL — 2605.24426v1 (2026-05-23)

**State:** policy weights, training interface, recent aggregate failure profile. **Proposal:** executable diagnosis activates schema, tool-affordance, recovery or capability cues; no general code-population search. **Verifier:** unchanged parser/schema/execution/state and terminal task checker. **Failures:** turn labels feed interface adaptation and diagnosis-weighted GRPO; specific candidate no-gain/rejection/rollback rule NR. **Partial:** graded diagnostic utility changes advantages, not binary task reward. **Memory:** trajectory buffer; logged round profiles, interface states and validation/configuration. **Budget:** 400 prompts, batch 32, eight rollouts/prompt, 20 interaction steps; total rounds/stagnation rule NR. **Changes:** both policy and training wrapper; wrapper removed at evaluation. **Important implementation limit:** Appendix D.4 says main rerun activates only observation_lite schema annotation; feedback evolution and diagnostic evolution are optional templates. Do not treat all advertised adaptation components as established active experiment behavior.

[Primary: §§3.2–3.5, Appendix B–D, especially D.4](https://arxiv.org/html/2605.24426v1).

### 4. GenEnv — 2512.19682v2 (2025-12-23)

**State/object:** agent and simulator weights; expanding trace and generator-supervision pools. **Proposal:** simulator creates new task batches/variations from seeds and success summaries; not local code repair. **Verifier:** structured execution/exact targets, task-dependent similarity for free-form output; traces must parse/execute/be evaluable. **Response:** simulator rewarded near 50% agent success; batches beyond±0.1 excluded from simulator updates. Agent GRPO, simulator reward-weighted regression. **Failures:** malformed traces filtered; no explicit syntax/semantic repair, rollback, candidate acceptance or per-candidate regression gate. **Memory:** accumulated valid traces retain older curricula; weighted generator pairs. **Budget:** ten epochs each, batch 64, 9,000-token agent context; epoch-frequency dual updates; no convergence stopping rule. **Changes:** both policies and generated distribution. **Transfer:** success-band targeting is curriculum optimization with a changing learner; its objective differs from finding a beneficial LOW intervention for fixed policy.

[Primary: §§2.2–2.4, 4.1, Appendix A.2–A.3](https://arxiv.org/html/2512.19682v2). Paper-linked code, not inspected: follow abstract's repository link.

### 5. Agent-World — 2604.18292v1 (2026-04-20)

**State/object:** tool/database ecosystem, taxonomy arena, task population, policy weights. **Proposal:** diagnostic agent reads failed traces, validator output, error statistics and schemas; ranks weak environments and emits targeted task-generation instructions. Regenerate tasks; optionally complexify database state. **Verifier:** tool compilation and >50% associated unit tests; tasks use executable database/answer checks or rubric-conditioned LLM judgment. **Failure:** invalid tools filtered; capability failures drive new training population; semantic/no-gain/regression/rollback selection policies NR. **Memory:** databases, arena taxonomy, traces; rejected candidate snapshots NR. **Budget:** five arena environments/category; two self-evolution rounds reported; fixed round horizon, not convergence. **Changes:** continuing GRPO plus task/environment expansion. **Caveat:** prose calls database complexification optional; Algorithm 1 applies it to weak environments. **Transfer:** diagnosis-conditioned task synthesis supports an outer loop, not proven fixed-policy Rules-family calibration.

[Primary PDF: §§3.1, 3.2.2 Algorithm 1, 4.3.4](https://arxiv.org/pdf/2604.18292).

### 6. Don't Just Fine-tune the Agent, Tune the Environment — 2510.10197v2 (2026-01-30)

**State/object:** training feedback augmentation and policy checkpoint/curriculum stage. **Proposal:** generator reads error trajectories and domain examples; constitutional judge assesses actionability and solution leakage. **Repair:** rejected augmentation returns refined criteria to generator, maximum three attempts; approved feedback used in training. **Verifier:** judge for hints; executable state+result criteria for per-turn progress reward. **Partial:** fraction of successful turns supplies graded reward. **No gain/regression:** curriculum advances only when validation plateaus and gradient norm stabilizes; candidate-effect acceptance/rollback NR. **Memory:** checkpoints implied by stage selection; rejected-hint archive NR. **Budget:** four stages, 400 problems; three augmentation attempts, total proposal/rollout budget NR. **Changes:** policy learning throughout, feedback on stages 2–3 then off stage 4/evaluation. **Transfer:** closest co-evolution-side precedent for bounded semantically checked retry, but it repairs feedback validity, not demonstrated policy-relative LOW effect.

[Primary: §§3.2–3.4, Appendix B.3](https://arxiv.org/html/2510.10197v2). Paper-linked code: [EnvTuning](https://github.com/inclusionAI/AWorld-RL/tree/main/EnvTuning) (link target not independently inspected).

### 7. EnvScaler — 2601.05808v2 (2026-04-17)

**State/object:** Python class implementing state/rules/tools, documentation, schemas; then initial states, tasks, validators. **Proposal:** task-derived themes → plans → method code → assembly. **Verifier:** AST; frontend testing agent generates positive/negative calls, backend checker inspects code/results/state deltas. **Failure:** syntax-invalid files discarded; semantic score<0.85 discarded after 100 test rounds. This is assessment/filtering, not demonstrated repair of rejected environments. **Partial:** fraction of terminal checklist validators passed is trajectory reward. **No gain/regression/rollback:** NR. **Memory:** generated environments/tasks/trajectories, no rejected-node search archive described. **Budget:**191 retained environments, ≈7K scenarios; 100 assessment rounds; no candidate-improvement stopping rule. **Changes:** new environment population; later SFT/RL updates learner. **Transfer:** state-grounded test separation and valid/invalid action tests; scaling gains cannot establish effectiveness of a LOW search controller.

[Primary: §§3.2–3.4, 4.2, 5.1](https://arxiv.org/html/2601.05808v2). Paper-linked code: [EnvScaler](https://github.com/RUC-NLPIR/EnvScaler) (not inspected).

### 8. VeriEnv — 2603.10505v1 (2026-03-11)

**Title:** Safe and Scalable Web Agent Learning via Recreated Websites. **State:** cloned code/database/Python SDK, tasks/validators, learner. **Proposal:** coding agent builds from screenshots; Playwright interactions reveal discrepancies and prompt incremental bug patches. **Verification:** execute SDK task feasibility and terminal predicates. **Failure:** construction issues return to coding agent; successful trajectories alone enter rejection fine-tuning. Candidate no-gain/regression rollback and rejected-snapshot memory NR. **Budget:**149 website collection; 97 training sites; 83.5min/$3.6 mean construction including debugging/tasks; numeric repair cap and learning rounds NR in inspected text. **Changes:** site construction then learner/self-generated tasks; fixed-site mastery does not require environment edits. **Caveats:** human audit found 90% task executability, 76% judge correctness; deterministic predicates do not guarantee correct criteria/reset handling. RL is future work (§6.2), not the reported rejection-fine-tuning method.

[Primary: §§3.1–3.4, 4.1–4.2, 6.2](https://arxiv.org/html/2603.10505v1). Paper promises [VeriEnv repository](https://github.com/kyle8581/VeriEnv) upon acceptance; availability not independently checked.

### 9. Agent World Model (AWM) — 2602.10090v3 (2026-05-22)

**State/object:** SQLite schema/data, MCP tool schemas/code, task verification logic. **Proposal:** scenario/task-conditioned staged code generation. **Repair:** run each component in isolation; return exception and problematic code to LLM for corrected regeneration, up to five iterations or successful execution. **Verifier:** construction execution; downstream code signals plus LLM judge labels completed/partial/agent-error/environment-error. **Partial:** explicitly distinguished. **No gain/regression:** no fixed-policy effect optimization or regression-gated candidate selection. **Memory/rollback:** candidate snippet/error persists in retry; population archive/rejected snapshots/rollback NR. **Budget:**1,000 environments, 10,000 tasks; allows up to 10% stage errors for cost. **Changes:** generated environment population, then agent RL. **Transfer:** bounded error-conditioned code repair is direct mechanism precedent; successful execution alone does not show semantic correctness or control over a fixed learner's performance.

[Primary: §§3.3.1–3.3.2, 4.1](https://arxiv.org/html/2602.10090v3). Paper-linked code: [agent-world-model](https://github.com/Snowflake-Labs/agent-world-model) (not inspected).

### 10. Qwen-AgentWorld — 2606.24597v1 (2026-06-23)

**Title:** Language World Models for General Agents. **Main object:** language world-model parameters predicting environment responses; continual pretraining/SFT/RL, not executable Rules-family search. **Distinct inner optimizer (§3.1.2):** agent studies real trajectory patterns/errors, writes or revises simulator system prompt, evaluates frozen world-model predictions against held-out real responses using separate judge, reads scores/concrete errors and revises again. **Budget:**10 propose–evaluate–refine cycles per run; 12 parallel style-seeded runs; human review/approval of final templates. **Failures:** prediction errors yield targeted revision; explicit syntax/no-gain/regression decision rules, best-so-far restoration, rejected archive and automatic rollback NR. **Memory:** current template and prediction feedback; persistent lineage archive NR. **Changes:** prompt in this sub-loop; simulator and agent training in wider system. **Transfer:** concrete repeated semantic-error feedback, but its judge-based fidelity objective and human final gate differ from LOW's fixed executable contract.

[Primary: §3.1.2 AutoResearch, §§3, 6](https://arxiv.org/html/2606.24597v1).

### 11. PhoneWorld — 2605.29486v2 (2026-08-14)

**State/object:** app PRD, Kotlin/Compose code, readonly content, resettable SQLite state, construction skill/checklist/component library. **Proposal:** coding agent implements recovered screen/transition requirements; compile/self-review detects issues; human comparisons supply additional reports. **Repair:** rebuild/retest same app after syntax/runtime/navigation/UI issues. **Memory:** catalogued failures expand checklist; 18 reusable modules and construction skills transfer across apps; rejected snapshots/rollback NR. **Verifier:** compilation, emulator smoke flows, human audit, database/key-value task checks. **Budget:** usually1–2 human review rounds; 34 apps/16 domains; autonomous iteration cap NR. **No gain/regression/partial:** no fixed-policy search acceptance rule; downstream supervised learning and separate RL study. **Transfer:** persistent failure checklist plus reusable safe components, while construction involves human review and does not establish autonomous tuning to a learner target.

[Primary: §§3.3–3.6, 4–5](https://arxiv.org/html/2605.29486v2).

### 12. Self-Improvements in Modern Agentic Systems: A Survey — 2607.13104v1 (2026-07-14)

Taxonomy: updates to model parameters versus prompts/memory/tools/control scaffold; updates are induced by experience and committed persistently. Version history supports validation/rollback conceptually. Distinguishes evaluation substrates and ordinary within-task iteration from persistent self-improvement. Useful for classifying AEA's fixed-policy optimizer and the future learning loop; not empirical evidence of any particular retry policy. Primary trails: DGM, HGM, Live-SWE-Agent, and skill/scaffold evolution. No experimental proposer, iteration budget, candidate rejection or rollback implementation to audit in the survey itself.

[Primary: §§3–4, 6.4, 7.1](https://arxiv.org/html/2607.13104v1).

### 13. Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops — 2607.07663v2 (2026-09-06)

Organizes 1250 papers by update target (deployment behavior, trained policy, evaluator, research process) and degree of loop closure. Evaluator reliability is a recurring bottleneck; persistent scaffold changes require validation. Supports calling LOW a bounded fixed-policy optimization problem, not open-ended RSI merely because a proposer is called repeatedly. Treat as a literature map, not a measured closed-loop system; its per-system round, rejection, memory and rollback claims require original-paper verification. Followed its DGM trail and cross-checked other primary references; survey dated within audit cutoff.

[Primary: §§1–3, especially3.4](https://arxiv.org/html/2607.07663v2).

## 4. Additional mechanisms found through search and citations

### TE — Environment Evolution for Terminal Agents [P,E]

[Primary: §§4.1–4.2, 5.2](https://arxiv.org/html/2609.04128v1#S4).
Object: executable environment/instruction/verifier lineage. Proposer edits a scenario–skill
sequence; reviewer gates the plan. Modifier applies a residual environment change. Oracle
solution, no-op invalid-solution and rubric checks gate the candidate; failed directions
trigger repair or restart from the accepted parent using another direction. All three
directions exhausted ends the branch. Numeric repair cap, rejected archive and automatic
regression rollback: NR. Human-discovered defects update rubrics during development.
Experiments cap lineages at 15 generations. Construction is off-policy; learner training uses
an 8-rollout scheduler that advances after pass rate exceeds 6/8. It is not on-policy LOW
mechanism optimization. Syntax versus other repair is not separately specified. Accepted
environments persist; training changes the policy.

**AEA inference:** a failed semantic direction can warrant replacement while a realizable
plan warrants code repair. Do not borrow mutable verifiers or policy-independent “harder”
objectives for the immediate LOW problem.

### GP — GEPA [P,E]

[Primary PDF: §3, Algorithms1–2, Appendix E](https://arxiv.org/pdf/2507.19457).
Object: module prompts; frozen weights/control flow. Reflection model reads parent prompt,
execution traces, scores and textual evaluator feedback; mutates a module or merges parents.
State: candidate population, ancestry and per-task validation scores. A child must improve
its feedback minibatch before population admission/full selection evaluation; nonimproving
children are discarded, parents retained. Per-instance Pareto selection permits alternatives
to the aggregate champion. Final artifact maximizes aggregate selection performance.
Syntax/semantic-specific repair and persistent rejected-edit buffer: NR. Parent retention
provides recovery without replacing the live champion. Budget is rollout cap B; experimental
minibatch3, optional merges ≤5, benchmark-specific caps. No learner-weight or environment
update in the standard loop. Type: reflective evolutionary search.

**AEA inference:** retain concrete evaluator feedback, and charge selection evaluations.
Per-task Pareto populations become more natural for reusable families across multiple tasks
than for four binary samples from a single LOW task.

## 5. Method–mechanism matrix

The two panels are one matrix split for readability; join on method ID. Details and evidence
qualifications are in the cards. `NR` is deliberate. `ref`=reference; `val`=selection validation;
`traj`=trajectories; `inc`=incumbent; `pop`=population. Budgets are native-paper settings, not
AEA budget recommendations. Repeated use of a candidate score is not new independent evidence.

### Panel A — object, evidence and evaluation

| Method | Optimization object | One-shot / iterative | Candidate representation | Feedback source | Verifier | Performance measurement |
|---|---|---|---|---|---|---|
|Current AEA LOW|Environment|One-shot DESIGN|W(d) code|Original failures+ref|Smoke/privilege/oracle|4→8; K16 external|
|EH EnvHarness|Environment|Iterative|Component set|Fresh traj|Task+designer|Success/failure distribution|
|HE HarnessEvolve|Harness|Iterative|Harness delta|Ref diagnosis|Quality+replay|Batch/val accuracy|
|SO SkillOpt|Skill|Iterative|Bounded text edits|Scored traj|Val gate|Selection score|
|RS Rethinking Skills|Skill|Iterative|Revised text|Feedback view|Val gate|Val/test|
|RE Rethinking Harness|Comparison framework|Varies|Response/harness|Matched feedback|Task verifier|Transfer/budget|
|HELIX|Harness|Enumerated round|Typed recipe|Sibling outcomes|Conformance/tests|Fixed/union separate|
|MetaSkill-Evolve|Task/meta skills|Iterative|Files/DAG|Failure+history|Val delta|Gain|
|SEAL|Learning interface|P iterative; E limited|Cue wrapper|Turn diagnosis|State/schema|Task/diagnostic|
|GenEnv|Simulator+policy|Iterative|Weights/tasks|On-policy success|Task-dependent|Difficulty band|
|Agent-World|Task ecosystem|Iterative|Tools/tasks/database|Failures|Tests/rubric|Weak-environment scores|
|Environment Tuning|Training feedback|Iterative|Augmentation|Error traj|Judge+state|Progress/val|
|EnvScaler|New environments|Construction/filter|Python/tools|Test calls|AST/backend|Semantic score|
|VeriEnv|Website clones|Construction repair|Code/SDK|Interaction discrepancies|Task predicates|Training/evaluation|
|AWM|Environment code|Construction repair|SQLite/MCP|Exceptions|Execution/judge|Task outcomes|
|Qwen-AgentWorld|Simulator prompt/model|Iterative|Prompt/weights|Prediction errors|Response judge|Fidelity|
|PhoneWorld|App clone|Construction repair|Kotlin/SQLite|Build/human|Emulator/state|Task outcomes|
|DG DGM|Agent code|Evolutionary|Repository|Benchmark logs|Compile/edit/tests|Coding score|
|AE AlphaEvolve|Program|Evolutionary|Diff/code|Outputs/scores|Cascade|Application metric|
|TE Terminal Evolution|Environment lineage|Iterative|Plan/residual|Review/checks|Oracle/no-op/rubric|Difficulty; scheduler|
|GP GEPA|Prompts|Evolutionary|Module text|Traces/errors|Minibatch/val|Task scores|

### Panel B — memory, repair, selection and cost

Cells pointing to **card** inherit the explicit failure/stop/number details above; this keeps
the comparison readable without suggesting identical budgets across different systems.

| Method | Candidate memory | Best-so-far memory | Repair mechanism | Selection/gating | Rollback | Population / single | Inner-loop budget | Outer loop / co-evolution | Relevance to LOW (our judgment) |
|---|---|---|---|---|---|---|---|---|---|
|Current AEA LOW|Audit only|None|None|Hard filters+dose|None|≤ 2 prewritten|30 incl estimate; 1 call|Outside method|Missing feedback edge|
|EH|Candidate/stack|NR|Rewrite|Designer validation|NR|Stack|Card|Learning between|Direct comparator|
|HE|Ref/replay|Snapshots|Quality rejection|Batch+replay|Snapshot selection|Inc+snapshots|Card|No weights|Gate discipline|
|SO|Rejected edits|Best skill|Localized patch|Strict gain|Retain inc|Single|Card|Meta guidance|Artifact optimization|
|RS|Inc only|Separate best|Revision|Nondecrease|Retain inc|Single|Card|None|Sparse progress|
|RE|Varies|Varies|Varies|Matched evaluator|Varies|Varies|K|Transfer assessment|Budget control|
|HELIX|Sibling dataset|Measured portfolio|NR|Conformance|NR|65 recipes|Card|Proposed only|Provenance, caveat|
|MetaSkill|DAG/history|Positive archive|Child edits|Positive parent gate|Restore parent|Frontier|Card|Meta updates|Too large initially|
|SEAL|Profiles|NR|Cue adaptation|NR|NR|Training stream|Card|Policy/interface|Later, limited E|
|GenEnv|Data pools|NR|New tasks|Difficulty filter|NR|Batches|Card|Both weights|Curriculum analogy|
|Agent-World|Arena/database|NR|New tasks|Tests/capability|NR|Population|Card|Policy+tasks|Later curriculum|
|Environment Tuning|Stages|NR|Hint retry|Constitution/val|NR|Staged|Card|Policy training|Semantic checks|
|EnvScaler|Generated pool|NR|Filtering|AST/score|NR|Population|Card|Later training|Gate examples|
|VeriEnv|Clone state|NR|Bug patches|Predicates|NR|Many sites|Card|Later RFT|Construction only|
|AWM|Snippet/error|NR|Regenerate|Execution|NR|Many worlds|Card|Later RL|Mechanical repair|
|Qwen-AgentWorld|Prompt/errors|NR|Prompt revision|Fidelity/human|NR|12 seeds|Card|Wider training|Semantic feedback|
|PhoneWorld|Checklist/library|NR|Rebuild|Build/human|NR|Many apps|Card|Later training|Reusable safeguards|
|DG|Functional archive|Scores|Self-edit|Functional admission|Parent lineage|Archive|Card|Code self-improves|RSI distinction|
|AE|Program database|Elites|Diff/rewrite|Evaluator cascade|Parents|Islands|Application cap|Optional meta|Cheap gates|
|TE|Accepted lineage|NR|Repair/change direction|Three gates|Parent restart|Lineages|Card|Scheduled RL|Typed failure routes|
|GP|Ancestry/scores|Selection best|Mutation/merge|Minibatch then val|Parents|Pareto pool|B|None|Feedback+budget|

## 6. Feedback routing: transfer assessment

| Feedback type | Current automated LOW | Proposed owner | What the feedback must contain |
|---|---|---|---|
| Structural | Filter proposal, try already-generated sibling | Deterministic tooling or designer code repair | Exact exception/API/schema location, candidate hash, violated contract |
| Privilege / task preservation | Reject | Designer semantic replacement; hard independent gate | Forbidden information class and provenance; no bypass instructions |
| Solvability | Reject candidate | Designer revise mechanism; infrastructure separately | Guard status and failing step, distinguished from expert timeout/unavailability |
| Behavioral leverage | Endpoint too_hard ends family | Designer mechanism revision/replacement | s/n plus blocked/no-effect actions and observations under this candidate |
| Calibration | Controller changes d inside frozen family | Controller first; one bounded redesign only if budgeted | Ordered measurements, bracket, remaining budget, observed jump or reversal |
| Independent confirmation | Experimental report only | Evaluation only | Never supplied to the optimizer |

This routing is **our proposed synthesis**. No reviewed method establishes that these exact
routes will work on ALFWorld LOW. The useful commonality is externally judged candidate
updates; the methods differ sharply in what persists and what failure actually triggers repair.

## 7. What to borrow, and what to leave out

Borrow precise failure feedback, bounded proposal budgets, persistent candidate identity,
the last useful artifact, rejection summaries, fresh behavioral evaluation and independent
final reporting. Favor a small stateful optimizer over multiple critic/planner/ranker agents.

Do not borrow shared-harness clustering for one task, an LLM success judge in place of the
simulator, full simulator synthesis, optimizer meta-learning, unconstrained self-modification,
oracle best-of-population success as deployable performance, or a large population before
measuring simple sequential search. No study above makes the first generated program's
correctness a general requirement; neither does any guarantee that revision escapes a weak
support mechanism or creates a useful dose operating point.

The recommendation and its falsifiable experiment are in
[LOW_ITERATIVE_RSI_REDESIGN.md](LOW_ITERATIVE_RSI_REDESIGN.md).
