# E-obs-F follow-up report — generated 2026-09-06 02:48 UTC

PREREG2 sha `148ce76`; inputs E-obs @ `8ee43da`; Flash config sha256 `89857939f328dc86904cefe5ddf6f31286345294b35fdaee2f9f27940a972630`; follow-up spend (ledger phase flash_probe) USD 1.00 of the USD 10 cap; all other items LLM-free.

## F1 — Hardening breakdown on saturated tasks (H arm)

S_H (p5_H = 1.0): 17 tasks [0, 1, 2, 4, 5, 7, 8, 12, 13, 15, 16, 17, 20, 24, 25, 28, 29]; S_H' (p5_H >= 0.8): 21 tasks. Task classes on S_H: {'NOEFFECT-dominated': 16, 'SKIPPED(no validated attempt)': 1}; on S_H': {'NOEFFECT-dominated': 18, 'MIXED': 2, 'SKIPPED(no validated attempt)': 1}.

| attempt-level rate on failed attempts (S_H) | value |
|---|---|
| a = share NOEFFECT | 0.945 [0.882, 1.000] (n=55, tasks=16) |
| b = share OVERSHOOT ∪ ZERO | 0.036 [0.000, 0.083] (n=55, tasks=16) |
| c = share INBAND-but-not-accepted | 0.018 [0.000, 0.067] (n=55, tasks=16) |

S_H' (supplementary): a = 0.924 [0.857, 0.974] (n=66, tasks=19); b = 0.045 [0.000, 0.098] (n=66, tasks=19); c = 0.030 [0.000, 0.082] (n=66, tasks=19).

| controllability (S_H) | rate | CI | n | tasks |
|---|---|---|---|---|
| P(toward band | SR_i above band) | 0.222 | [0.111, 0.364] | 45 | 15 |
| P(toward band | SR_i below band) | 0.000 | [0.000, 0.000] | 2 | 2 |
| P(toward band | SR_i outside band) | 0.213 | [0.109, 0.350] | 47 | 15 |
| P(next milder (SR up) | ZERO or OVERSHOOT) | 1.000 | [1.000, 1.000] | 2 | 2 |
| P(next harder (SR down) | NOEFFECT) | 0.244 | [0.135, 0.378] | 45 | 15 |

Attempt classes on S_H (all validated attempts): {'INBAND': 3, 'NOEFFECT': 59, 'ZERO': 1, 'OVERSHOOT': 1}; attempts = 64.

**D1 outcome: expressivity branch (a ≥ 0.50)** — a met (CI-decisive), b not met (CI-decisive), c not met (CI-decisive).

## F2 — Certificate source decomposition

| arm | axis | n | R_old ok | R_old not run | R_exp ok / R_old fail | R_hint run | R_hint ok / R_exp fail | certified | unresolved | USD R_hint | USD per hint-certified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H | A | 30 | 19 | 1 | 7/11 | 13 | 4/4 | 30 | 0 | 0.0962 | 0.0241 |
| H | A+O | 3 | 1 | 0 | 0/2 | 2 | 0/2 | 1 | 2 | 0.1466 |  |
| H | A+T | 2 | 1 | 0 | 0/1 | 1 | 1/1 | 2 | 0 | 0.0034 | 0.0034 |
| H | O | 27 | 26 | 1 | 0/1 | 5 | 1/1 | 27 | 0 | 0.2182 | 0.2182 |
| H | S0 | 9 | 8 | 1 | 0/1 | 1 | 1/1 | 9 | 0 | 0.0038 | 0.0038 |
| H | S0+O | 1 | 0 | 1 | 0/1 | 1 | 1/1 | 1 | 0 | 0.0194 | 0.0194 |
| H | T | 32 | 23 | 9 | 0/9 | 11 | 9/9 | 32 | 0 | 0.1574 | 0.0175 |
| H | T+O | 1 | 1 | 0 | 0/0 | 0 | 0/0 | 1 | 0 | 0 |  |
| H | none | 1 | 0 | 1 | 0/1 | 1 | 1/1 | 1 | 0 | 0.0066 | 0.0066 |
| released | S0 | 13 | 12 | 1 | 0/1 | 2 | 1/1 | 13 | 0 | 0.0193 | 0.0193 |
| released | T | 5 | 4 | 1 | 0/1 | 1 | 1/1 | 5 | 0 | 0.0042 | 0.0042 |

Cost: R_old and R_exp are LLM-free (one env session each, ~1.5–5 s). R_hint spent USD 0.68 in total over the Phase-3 run and certified 20 candidates that neither replay certified, i.e. USD 0.034 per hint-certified candidate. O5H detail: among the 21 certified A/T candidates with R_old = 0, the certifying source was {'R_exp': 7, 'R_hint': 14}; their R_old reasons were {'blocked': 11, 'not_run': 10} ('not_run' = the task has no base expert witness).

## F3 — Expert A/A on recoverability prefixes

| statistic | value |
|---|---|
| prefix flip rate P(not all three equal) | 0.114 [0.046, 0.200] (n=1785, tasks=19) |
| P(C_1 = 1 | C_any3 = 1) | 0.827 [0.693, 0.930] (n=718, tasks=19) |
| expert failure rate from reset on these tasks (witness attempts) | 0.211 (57 attempts on 19 tasks) |
| share L_1 >= 2 | 0.943 [0.857, 1.000] (n=35, tasks=19) |
| share L_any3 >= 2 | 0.943 [0.857, 1.000] (n=35, tasks=19) |
| share non-monotone (attempt 1) | 0.571 [0.368, 0.778] (n=35, tasks=19) |
| share non-monotone_any3 | 0.514 [0.306, 0.714] (n=35, tasks=19) |
| share non-monotone_maj3 | 0.486 [0.286, 0.694] (n=35, tasks=19) |
| n trajectories / prefixes | 35 / 1785 |

**D2 outcome: a recoverability certificate needs ≥ 3 expert attempts (or a policy-success suffix) per state; bisection stays inadmissible (non-monotone_any3 ≥ 0.20; PREREG O6 stands); CHS branch kept (L_any3 ≥ 2 share ≥ 0.50)** — flip met (CI not decisive); non-monotone_any3 met (CI-decisive); L_any3 ≥ 2 met (CI-decisive). n = 35 trajectories (35, not 40: see measurement notes).

## F4 — Witness ladder and the expert-failure tasks

| witness | coverage |
|---|---|
| W_policy | 0.967 [0.900, 1.000] (n=30, tasks=30) |
| W_expert1 | 0.867 [0.733, 0.967] (n=30, tasks=30) |
| W_expert3 | 0.867 [0.733, 0.967] (n=30, tasks=30) |
| W_any | 1.000 [1.000, 1.000] (n=30, tasks=30) |

Task 2: p16 = 0.9375; candidates = 2 (H 2); certified = 2; certificate sources: {'R_hint': 2}; R_old reasons: {'not_run': 2}; policy-success witness available: True.
  R_old_policy (verbatim replay of the shortest successful Pro baseline trajectory, 16 steps): pass 2/2; fails: [].

Task 4: p16 = 1.0; candidates = 4 (H 4); certified = 4; certificate sources: {'R_hint': 4}; R_old reasons: {'not_run': 4}; policy-success witness available: True.
  R_old_policy (verbatim replay of the shortest successful Pro baseline trajectory, 12 steps): pass 4/4; fails: [].

Task 5: p16 = 0.875; candidates = 5 (H 3); certified = 5; certificate sources: {'R_hint': 5}; R_old reasons: {'not_run': 5}; policy-success witness available: True.
  R_old_policy (verbatim replay of the shortest successful Pro baseline trajectory, 10 steps): pass 5/5; fails: [].

Task 22: p16 = 0.8125; candidates = 5 (H 5); certified = 5; certificate sources: {'R_hint': 5}; R_old reasons: {'not_run': 5}; policy-success witness available: True.
  R_old_policy (verbatim replay of the shortest successful Pro baseline trajectory, 21 steps): pass 5/5; fails: [].

No Phase-3 certificate on these four tasks used a policy-success witness: R_old was skipped ('not_run') because W_base failed, so certification came from R_exp/R_hint; R_old_policy above is the supplementary certificate.

## F5 — Flash policy probe

| consumer | zero | edge-low | band | edge-high | saturated |
|---|---|---|---|---|---|
| Pro p16 | 0.033 [0.000, 0.100] | 0.133 [0.033, 0.267] | 0.200 [0.067, 0.333] | 0.267 [0.133, 0.433] | 0.367 [0.200, 0.533] |
| Flash p8 | 0.000 [0.000, 0.000] | 0.033 [0.000, 0.100] | 0.200 [0.067, 0.367] | 0.167 [0.033, 0.300] | 0.600 [0.433, 0.767] |

Mean success: Pro p16 0.738, Flash p8 0.867. zero + edge-low share: Flash 0.033 [0.000, 0.100] (n=30, tasks=30); Pro 0.167 [0.033, 0.300] (n=30, tasks=30).

**D3 outcome: CHS is evaluated in the RL Study only (Flash zero + edge-low < 0.30)** — not met (CI-decisive).

Flash recoverability (single expert attempt, 1 failed trajectories from tasks with p8 ≤ 0.2, ≤ 1 per task, seed 20260908): L ≥ 2 share 0.000 [0.000, 0.000] (n=1, tasks=1); non-monotone share 0.000 [0.000, 0.000] (n=1, tasks=1).

## F6 — Candidate taxonomy (dose parameters in the wild)

H arm (106 candidates) operator types: {'A:block(literal)': 28, 'T:nothing_happens': 21, 'O:admissible': 15, 'O:text': 12, 'S0:setup_actions': 9, 'T:text_edit': 9, 'A:block(literal)+O:text': 2, 'T:nothing_happens+random': 2, 'A:block(literal)+T:text_edit': 2, 'A:block(regex)': 2, 'S0:setup_actions+O:admissible': 1, 'none': 1, 'T:nothing_happens+random+O:text': 1, 'A:block(literal)+O:admissible': 1}.
Released arm operator types: {'S0:setup_actions': 13, 'T:nothing_happens+random': 5}.
H-arm candidates carrying an explicit numeric parameter other than 0/1: 31/106 = 0.292.

### 15 candidates for manual review (random, seed 20260909)

#### ff78d1aa — task 3, axis S0, SR_c 0.4, decision accept
rationale: Baseline SR is 0.80; recent 15 accepted episodes show 0.67, still too easy by 0.07. The failed trajectory shows the Policy wandering aimlessly (opening cabinets/drawers) when it loses track of the egg's location — a failure-recovery weakness. I'll target the S0 axis (weight 0.3, under-represented) b
in_env_actions: ['take egg 1 from countertop 1']
```python
(no rules_code)
```

#### 3279820c — task 2, axis S0+O, SR_c 0.4, decision accept
rationale: Baseline SR is 1.00 and current accepted SR is 0.80, both above the [0.40,0.60] band. The task is "put two lettuce in fridge" — a multi-step pickup/carry task. I'll exercise failure-recovery via the S0 axis: pre-place one lettuce already in the fridge so the Policy must notice only one remains on th
in_env_actions: ['take lettuce 1 from countertop 2', 'go to fridge 1', 'open fridge 1', 'put lettuce 1 in/on fridge 1']
```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Keep surface presentation intact; only trim the command list
        # while carrying an item to force reach-planning.
        text = obs.text
        carrying = "You are carrying:" in text
        cmds = env_state.admissible_commands
        if carrying and len(cmds) > 6:
            # Drop 'examine' and 'look' style commands so the Policy must
            # commit to go/take/put instead of exploring.
            kept = [c for c in cmds if not c.startswith("examine") and c != "look" and c != "inventory"]
            if kept:
                cmds = kept
        return Observation(text=obs.text, data={**obs.data, "admissible_commands": cmds})

```

#### e1d5baf3 — task 7, axis A, SR_c 1.0, decision reject
rationale: Baseline SR is 1.00; recent accepted episodes show SR 0.65, slightly too easy. The task is a short pick-and-place (statue to sidetable) with a fast path. I'll add a narrow A-axis restriction that blocks a redundant-but-harmless command the policy sometimes issues, forcing it to pick the correct obje
in_env_actions: []
```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        text = action.kwargs.get("text", "").strip().lower()
        # Block non-progressing exploration commands to force focused action.
        if text in ("look", "inventory", "help"):
            return Blocked(reason="redundant exploration command blocked")
        return action

```

#### 42f8a147 — task 28, axis A+O, SR_c 1.0, decision reject
rationale: Baseline SR is 1.00 (5/5) with a fast 9-step solution available, so there is headroom to add difficulty. The objective wants SR in [0.40,0.60] and recent traces show all-success with no failure-axis signal, so I'll add a subtle A-axis perturbation that forces failure-recovery: block "go to" commands
in_env_actions: []
```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Only act on the 'do' tool.
        if action.name != "do":
            return action
        text = action.kwargs.get("text", "")
        if not isinstance(text, str) or not text:
            return action
        # Block commands that are NOT in the admissible set. The policy
        # occasionally emits a stale/guessed command; rejecting it forces
        # it to recover by reading the admissible list again. This never
        # blocks a legal move, so the task stays solvable.
        admissible = env_state.admissible_commands or []
        if text not in admissible:
            return Blocked(reason="command not admissible; re-read admissible commands")
        return action

    def filter_observation(self, obs, env_state):
        # Occasionally hide ONE admissible command to force the policy to
        # re-derive navigation rather than pattern-match. Keep the winning
        # path reachable by never hiding more than one command per step.
        data = obs.data
        admissible = data.get("admissible_commands")
        if not isinstance(admissible, list) or len(admissible) <= 1:
            return obs
        # Deterministic-ish: hide based on step parity so behavior is stable
        # across rollouts and not random noise.
        if env_state.step_count % 3 == 0:
            new_admissible = admissible[1:]
            new_data = {**data, "admissible_commands": new_admissible}
            return Observation(text=obs.text, data=new_data)
        return obs

```

#### 9230a632 — task 13, axis A, SR_c 1.0, decision reject
rationale: Baseline SR is 1.00 (task is trivial for the Policy). The shortest solution is 7 steps: go to countertop 2, take mug, go to sinkbasin, clean, go to coffeemachine, put mug. To exercise failure-recovery without shifting surface presentation, I'll use the A axis to block the first 'take mug 1' attempt 
in_env_actions: []
```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Block the first mug pickup attempt to force a retry/recovery loop.
        if action.name == "do":
            text = action.kwargs.get("text", "")
            if "take mug 1" in text and "countertop 2" in text:
                extras = env_state.extras
                if not extras.get("mug_take_blocked"):
                    extras["mug_take_blocked"] = True
                    return Blocked(reason="mug pickup blocked once to force recovery")
        return action

```

#### 7752bf69 — task 4, axis S0, SR_c 0.8, decision accept
rationale: Baseline SR=1.00 and recent traces show the Policy solving this task robustly with no-op/exploration mutations having no effect. To exercise failure-recovery without shifting surface presentation, I use an S0 mutation via in_env_actions: pre-place one toiletpaper into a drawer before the policy star
in_env_actions: ['go to toilet 1', 'take toiletpaper 1 from toilet 1', 'go to drawer 2', 'open drawer 2', 'put toiletpaper 1 in/on drawer 2', 'close drawer 2']
```python
(no rules_code)
```

#### 673f445a — task 11, axis O, SR_c 0.0, decision reject
rationale: Baseline SR is 0.20 (weak Policy). The failure mode is clear: the failed trajectory loops on open/close cabinet 1 (repetition), never finding the cup. The successful trajectory required ~48 steps of wandering. Prior mutations were marked unsolvable/ineffective. I'll make a mild, solvable perturbatio
in_env_actions: []
```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Mild recovery nudge: when the Policy is looping (repetition_count >= 1),
        # append a neutral inventory reminder to the observation text WITHOUT
        # changing admissible_commands or the env's surface presentation.
        # This does not block any action and keeps the task fully solvable.
        if env_state.repetition_count >= 1:
            inv = env_state.inventory or []
            inv_str = ", ".join(inv) if inv else "nothing"
            new_text = obs.text + "\n\n[You are carrying: " + inv_str + "]"
            return Observation(text=new_text, data=obs.data)
        return obs

```

#### 320f421f — task 0, axis T, SR_c 0.8, decision accept
rationale: The previous T-axis mutation (forcing one failed cool) dropped SR from 1.00 to 0.60, but two rollouts timed out at 50 steps — the Policy apparently got stuck retrying cool in a loop or lost its way. The "Nothing happens" text may also shift presentation. I'll soften: instead of injecting a fake fail
in_env_actions: []
```python
class _Rules(Rules):
    def modify_transition(self, action, raw_response, env_state):
        cmd = action.kwargs.get("text", "")
        if "cool" in cmd and "fridge" in cmd:
            attempts = env_state.extras.get("cool_attempts", 0)
            env_state.extras["cool_attempts"] = attempts + 1
            # Only force a retry on the first cool attempt, and only if
            # we are early in the episode (step_count small). This keeps
            # the perturbation reachable and recovery short.
            if attempts == 0 and env_state.step_count <= 20:
                new_obs = Observation(
                    text="Nothing happens.",
                    data=raw_response.observation.data,
                )
                return EnvResponse(
                    observation=new_obs,
                    reward=raw_response.reward,
                    terminated=raw_response.terminated,
                    truncated=raw_response.truncated,
                    info=raw_response.info,
                )
        return raw_response

```

#### 3485b59d — task 10, axis O, SR_c 0.4, decision accept
rationale: Baseline SR is 0.0 with the Policy emitting empty actions (fail=policy_emits_empty_actions) — the Policy is stuck, not solving. The sample trajectory shows the Policy never heats the cup (it moves cup into microwave but never turns it on, then loses track). Since the Policy is already weak/failing, 
in_env_actions: []
```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Mild O-axis reinforcement: remind the Policy of the active goal
        # and current inventory-relevant progress without altering the
        # env's admissible commands or underlying state.
        goal = env_state.goal_text
        if goal and goal not in obs.text:
            obs = Observation(
                text=obs.text + "\n[Goal reminder: " + goal + "]",
                data=obs.data,
            )
        return obs

```

#### b335df2c — task 23, axis T, SR_c 1.0, decision reject
rationale: Baseline SR=0.80 with the Policy already grinding (one failure hit 50 steps, and a successful run shows repeated "Nothing happens" failures when trying to pick up a cd). The failure mode is the Policy issuing an ineffective action and getting stuck. I'll exercise failure-recovery by nudging the rewa
in_env_actions: []
```python
class _Rules(Rules):
    def modify_transition(self, action, raw_response, env_state):
        # When the env reports "Nothing happens", append a subtle hint
        # to the observation text so the Policy must notice the
        # ineffectiveness and re-plan instead of looping the same action.
        obs = raw_response.observation
        if "Nothing happens" in obs.text:
            new_text = obs.text + "\n[note: your last action had no effect; consider a different command]"
            return EnvResponse(
                observation=Observation(text=new_text, data=obs.data),
                reward=raw_response.reward,
                terminated=raw_response.terminated,
                truncated=raw_response.truncated,
                info=raw_response.info,
            )
        return raw_response

```

#### ff48e30f — task 24, axis A, SR_c 1.0, decision reject
rationale: Baseline SR is 1.00 and current accepted SR is 0.60 (in-band). Recent failures are all on the T axis, so I'll diversify by exercising the A axis: block a specific, recoverable command the Policy might attempt, without shifting surface presentation or making the task unsolvable.
in_env_actions: []
```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Inject a recoverable failure on the 'go to' navigation verb:
        # block the FIRST navigation attempt after the mug is picked up,
        # forcing the Policy to retry. Never blocks cooling/opening/putting,
        # so the task remains solvable.
        text = action.kwargs.get("text", "")
        if action.name == "do" and text.startswith("go to "):
            if not env_state.extras.get("nav_blocked_once"):
                if "mug 1" in env_state.inventory or "mug 1" in env_state.obs_text:
                    env_state.extras["nav_blocked_once"] = True
                    return Blocked(reason="navigation temporarily blocked to exercise retry")
        return action

```

#### 4d2e413d — task 0, axis T, SR_c 0.6, decision refine
rationale: Baseline is 1.00 SR with 15.4 avg steps. The Policy solves via a clean path: find apple, take it, cool it in fridge, put in garbagecan. To exercise failure-recovery without shifting surface presentation, I'll introduce a mild T-axis perturbation: when the Policy tries to cool the apple, inject a tra
in_env_actions: []
```python
class _Rules(Rules):
    def modify_transition(self, action, raw_response, env_state):
        cmd = action.kwargs.get("text", "")
        if "cool" in cmd and "fridge" in cmd:
            # Force one retry: first cool attempt reports failure.
            attempts = env_state.extras.get("cool_attempts", 0)
            env_state.extras["cool_attempts"] = attempts + 1
            if attempts == 0:
                new_obs = Observation(
                    text="Nothing happens.",
                    data=raw_response.observation.data,
                )
                return EnvResponse(
                    observation=new_obs,
                    reward=raw_response.reward,
                    terminated=raw_response.terminated,
                    truncated=raw_response.truncated,
                    info=raw_response.info,
                )
        return raw_response

```

#### 56803e98 — task 9, axis A+T, SR_c 1.0, decision reject
rationale: Baseline SR is 0.80 with a fast 8-step solution (navigate to shelf 2, take alarmclock 1, use desklamp). The failure trajectory shows the policy loops on "facing shelf 2, nothing" — it can't recover when its pick-up attempt is ineffective. To exercise failure-recovery without shifting surface present
in_env_actions: []
```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Block taking the alarmclock until the desklamp has been used,
        # forcing the policy to recover from an ineffective pick-up.
        if action.name == "do":
            text = action.kwargs.get("text", "")
            low = text.lower()
            if low.startswith("take alarmclock") and "use desklamp" not in env_state.extras.get("used_lamp", ""):
                return Blocked(reason="alarmclock is not visible until the lamp is lit")
        return action

    def modify_transition(self, action, raw_response, env_state):
        if action.name == "do":
            text = action.kwargs.get("text", "").lower()
            if text.startswith("use desklamp"):
                env_state.extras["used_lamp"] = "use desklamp"
        return raw_response

```

#### f1e08e33 — task 27, axis O, SR_c 0.6, decision accept
rationale: Baseline SR is 0.40 (2/5) — the Policy is weak but can solve. The failed trajectory shows the Policy looping on open/close microwave with "Nothing happens" repeatedly, wasting steps. I'll exercise failure-recovery by making ineffective actions (which print "Nothing happens") more salient — injecting
in_env_actions: []
```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # When the last action was ineffective, add a lightweight recovery
        # cue to the observation text WITHOUT touching admissible_commands
        # or the underlying env surface. This exercises failure-recovery.
        if not env_state.last_action_was_effective:
            cue = "\n[recover: your last command had no effect; try a different admissible command]"
            return Observation(text=obs.text + cue, data=obs.data)
        return obs

```

#### 4af13ea7 — task 19, axis O, SR_c 0.2, decision reject
rationale: Baseline SR is 0.20 (1/5). The Policy already struggles, mostly wandering (50-step failures) and even the success took 32 steps with lots of aimless navigation. The failure trace shows a key weakness: after heating, the Policy put the plate on sidetable 1, then picked it back up and lost the goal st
in_env_actions: []
```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        if not env_state.last_action_was_effective and env_state.step_count > 0:
            # Nudge the Policy to recover when an action had no effect,
            # without changing the admissible-command surface.
            text = obs.text
            if "Nothing happens" in text:
                text = text.replace(
                    "Nothing happens.",
                    "Nothing happens. (Re-check the current state and your inventory.)"
                )
            return Observation(text=text, data=obs.data)
        return obs

```

## F7 — Acceptance discretion in the H arm

| statistic | value |
|---|---|
| accepted SR_c distribution | {"0.4": 6, "0.6": 6, "0.8": 7} |
| accepted outside [0.4, 0.6] | 7/19 = 0.368 |
| accepted SR_c values outside band | 0.8 0.8 0.8 0.8 0.8 0.8 0.8 |
| tasks without ACCEPT | 10 |
| of which best attempt in band | 0 |
| validation rollouts per ACCEPT (all H validation / accepts) | 530/19 |

Accepted outside [0.4, 0.6] (task-resampled): 0.368 [0.158, 0.579] (n=19, tasks=19).

## Measurement notes

- Sampling seeds: F3 20260907 (stratified: every task with a failed trajectory contributes 1, then second picks in shuffled task order; only 19 tasks have failed trajectories and 3 have a single one, so n = 35 < 40); F5 recoverability 20260908; F6 review list 20260909.
- F3 attempt 1 is the existing Phase-4 value; attempts 2 and 3 are fresh closed-loop expert runs through the same `recover.c_at` path with per-process bridge reuse; resumable by (trajectory_id, t, attempt).
- F5 runs the released Orchestrator baseline path (`_rollout_baseline_k`, K = 8, concurrency 8) on a config differing from corpus_eobs.yaml only in the policy model id (test followup/tests/test_flash_config.py); prompt identity to Phase 1 on task 0 is recorded in LOG.
- The ledger's one truncated line (from the 2026-09-05 kill) is skipped by the readers; nothing was rewritten.

## Caveats

- Same substrate caveats as E-obs (single benchmark, N = 30, DeepSeek backbones, stochastic handcoded expert, 50-step env cap).
- F1 classes use the App. G band [0.4, 0.6] inclusive on K = 5 (SR ∈ {0, .2, .4, .6, .8, 1}); 'failed attempt' = decision ≠ ACCEPT. Task 17 in S_H had no validated attempt (skipped) and enters no attempt-level rate.
- F5 compares p8 (Flash) with p16 (Pro); the regime bins are the same but the resolutions differ (1/8 vs 1/16).
