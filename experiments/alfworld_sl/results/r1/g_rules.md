# Accepted rules of the released-designer arms G and G+ (Round 1)

Hooks: filter_action = A axis, modify_transition = T, filter_observation = O (envharness/harnesses/rules.py). p16 = successes/16 at the K=16 confirmation (baseline = shared original environment; env = the accepted environment). Intent = first sentence of the designer's rationale. No LLM call.

## Taxonomy

| arm | task | axes | Blocked( | Nothing happens | admissible edit | numeric constants | setup actions | baseline p16 | env p16 | learnable | intent |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G | 0 | A | y | - | - | 5 | 3 | 1.00 | 0.25 | y | The previous attempt successfully reduced the success rate to 80%. |
| G | 2 | A | y | - | - | - | 4 | 0.88 | 0.19 | - | The previous attempt failed to reduce the success rate because the pre-actions were not specific enough. |
| G | 4 | AO | y | - | y | 30 | 1 | 0.88 | 0.62 | y | The previous attempt had an SR of 0.80, which is above the target band [0.40, 0.60]. |
| G | 5 | AO | y | - | y | 2, 3, 4, 5 | 0 | 0.94 | 1.00 | - | The previous mutation was too aggressive, dropping the success rate from 0.8 to 0.2, which is below the target band [0.4, 0.6]. |
| G | 8 | O | - | - | y | 3 | 0 | 0.94 | 0.75 | y | The current success rate is perfect (0.50), hitting the center of the target band. |
| G | 15 | O | - | - | y | - | 2 | 0.75 | 0.56 | y | The previous attempt (redacting admissible_commands) was only partially effective, yielding 80% success. |
| G | 24 | - | - | - | - | - | 0 | 0.62 | 0.38 | y | The previous O-axis mutation (redacting the 'Admissible commands' list) caused the success rate to drop to 0.20, which is below the target band of [0.40, 0.60]. |
| G | 27 | O | - | - | - | 20 | 4 | 0.75 | 0.62 | y | The current success rate (0.65) is slightly above the target band (0.40 - 0.60). |
| Gplus | 0 | TO | - | - | y | 8, 10, 16, 70, 100 | 3 | 1.00 | 0.88 | - | The agent is performing well (SR 1.00) even with the existing redaction and truncation. |
| Gplus | 4 | O | - | - | y | 0.8, 8, 16, 10000 | 0 | 0.88 | 0.62 | y | The previous 50% FooterMask still yielded 80% success rate, which is above the target range [0.4, 0.6]. |
| Gplus | 5 | T | - | - | - | 25 | 0 | 0.94 | 0.44 | y | The current success rate of 0.60 is just at the upper edge of the target band [0.40, 0.60]. |
| Gplus | 8 | O | - | - | y | 0.8, 8, 16, 80, 10000 | 4 | 0.94 | 0.56 | y | The previous S0 attempt was invalid (empty/no-op actions). |
| Gplus | 10 | TO | - | - | y | 0.50, 8, 14, 16, 50, 10000 | 0 | 1.00 | 0.44 | y | The previous 0.8 success rate shows the task is still too easy. |
| Gplus | 14 | - | - | - | - | - | 4 | 0.94 | 0.88 | - | The previous S0 attempt using generic 'do' actions was ineffective, likely because 'do' without text is not a valid ALFWorld command or is ignored by the engine. |
| Gplus | 27 | O | - | - | y | 0.2, 8, 16, 20, 10000 | 0 | 0.75 | 0.62 | y | The current success rate (0.55) is within the target band [0.40, 0.60]. |

## Axis x leverage

| arm | axes | accepted envs | learnable (B_L) |
|---|---|---|---|
| G | - | 1 | 1 |
| G | A | 2 | 1 |
| G | AO | 2 | 1 |
| G | O | 3 | 3 |
| Gplus | - | 1 | 0 |
| Gplus | O | 3 | 3 |
| Gplus | T | 1 | 1 |
| Gplus | TO | 2 | 1 |

## Code of every accepted candidate

### G task 0 (candidate ca4832b1; accepted at 2/5 in search)

Setup actions: ['go to cabinet 1', 'go to cabinet 2', '']

```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        text = action.kwargs.get("text", "").lower()
        # Keep restricting exploration commands to force navigation
        if "examine" in text or "look" in text:
            return Blocked(reason="Exploration via examination/looking is restricted.")

        # Block opening fridge on the first 5 steps
        if "open fridge" in text and env_state.step_count < 5:
            return Blocked(reason="Fridge is stuck; try searching other areas first.")

        return action
```

### G task 2 (candidate 498228c5; accepted at 2/5 in search)

Setup actions: ['go to cabinet 1', 'open cabinet 1', 'examine cabinet 1', 'go to countertop 1']

```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Block examining cabinet 1 to force the agent to move to new locations.
        if action.name == "do":
            text = action.kwargs.get("text", "")
            if "examine cabinet 1" in text:
                return Blocked(reason="Cabinet 1 is already checked and empty.")
        return action
```

### G task 4 (candidate aae857a8; accepted at 2/5 in search)

Setup actions: ['go to cabinet 1']

```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Block 'examine' to force more navigation or memory-based action
        if env_state.step_count <= 30 and action.name == "do" and "examine" in action.kwargs.get("text", ""):
            return Blocked(reason="Examine is restricted early on.")
        return action

    def filter_observation(self, obs, env_state):
        # Continue restricting navigation to force thorough exploration
        if env_state.step_count <= 30:
            new_admissible = [
                cmd for cmd in obs.data.get("admissible_commands", [])
                if not cmd.startswith("go to")
            ]
            new_data = {**obs.data, "admissible_commands": new_admissible}
            return Observation(text=obs.text, data=new_data)
        return obs
```

### G task 5 (candidate fc328ea4; accepted at 4/5 in search)

Setup actions: none

```python
class _Rules(Rules):
    def filter_action(self, action, env_state):
        # Relaxed blocking frequency: every 5 steps instead of 2.
        if env_state.step_count % 5 == 0 and action.name == "do" and action.kwargs.get("text") == "go to drawer 1":
            return Blocked(reason="Drawer 1 is temporarily unavailable for pathing.")
        return action

    def filter_observation(self, obs, env_state):
        # Track step count locally in extras.
        if "step_counter" not in env_state.extras:
            env_state.extras["step_counter"] = 0
        env_state.extras["step_counter"] += 1

        # Trigger every 4 steps instead of 3, making it less intrusive.
        if env_state.extras["step_counter"] % 4 != 0:
            return obs

        parts = obs.text.split("Admissible commands: ")
        if len(parts) < 2:
            return obs

        cmd_list = parts[1].split(", ")
        # Redact only 2 commands instead of 5 to preserve more navigational options.
        if len(cmd_list) > 5:
            new_cmd_list = cmd_list[2:]
            new_text = parts[0] + "Admissible commands: " + ", ".join(new_cmd_list)
            return Observation(text=new_text, data=obs.data)

        return obs
```

### G task 8 (candidate f8106c58; accepted at 3/5 in search)

Setup actions: none

```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Occasionally redact the 'Admissible commands' section to force reliance on logic
        if env_state.step_count % 3 == 0:
            lines = obs.text.split('\n')
            new_lines = [line for line in lines if not line.startswith('Admissible commands:')]
            return Observation(text='\n'.join(new_lines), data=obs.data)
        return obs
```

### G task 15 (candidate 67af8af1; accepted at 3/5 in search)

Setup actions: ['go to cabinet 1', 'open cabinet 1']

```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Redact admissible_commands to force more robust planning
        if "admissible_commands" in obs.data:
            new_data = {k: v for k, v in obs.data.items() if k != "admissible_commands"}
            return Observation(text=obs.text, data=new_data)
        return obs
```

### G task 24 (candidate 0875cfe4; accepted at 3/5 in search)

Setup actions: none

```python
class _Rules(Rules):
    pass
```

### G task 27 (candidate 367e408d; accepted at 3/5 in search)

Setup actions: ['go to cabinet 1', 'open cabinet 1', 'go to drawer 1', 'open drawer 1']

```python
class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Add a subtle reminder if the agent is struggling,
        # but keep it neutral to maintain the surface presentation.
        if env_state.step_count > 20 and "You haven't found it yet" not in obs.text:
            return Observation(text=obs.text + "\n(Hint: Keep searching systematically.)", data=obs.data)
        return obs
```

### Gplus task 0 (candidate 80712fd9; accepted at 4/5 in search)

Setup actions: ['go to cabinet 1', 'open cabinet 1', 'go to countertop 1']

```python
import hashlib

class _Rules(Rules):
    def filter_observation(self, obs, env_state):
        # Increased redaction rate to 70% to force more robust planning
        step = int(getattr(env_state, "step_count", 0) or 0)
        digest = hashlib.sha256(f"{step}".encode("utf-8")).hexdigest()
        if (int(digest[:8], 16) % 100) < 70:
            text = obs.text
            cut = text.find("\n\nAdmissible commands: ")
            if cut >= 0:
                text = text[:cut]
            data = dict(obs.data or {})
            data.pop("admissible_commands", None)
            return Observation(text=text, data=data)
        return obs

    def modify_transition(self, action, raw_response, env_state):
        # T-axis: Truncate if taking too long (> 10 steps)
        if raw_response.info.get("won") is True or bool(getattr(env_state, "won", False)):
            return raw_response
        if int(getattr(env_state, "step_count", 0) or 0) >= 10:
            return EnvResponse(
                observation=raw_response.observation,
                reward=raw_response.reward,
                terminated=False,
                truncated=True,
                info={**raw_response.info, "reason": "too_many_steps"}
            )
        return raw_response
```

### Gplus task 4 (candidate af2e5fa1; accepted at 3/5 in search)

Setup actions: none

```python
import hashlib

class _Rules(Rules):
    DOSE = 0.8
    TASK_ID = "3a67f38f"

    def _masked(self, env_state):
        step = int(getattr(env_state, "step_count", 0) or 0)
        digest = hashlib.sha256(f"{self.TASK_ID}:{step}".encode("utf-8")).hexdigest()
        return (int(digest[:8], 16) % 10000) < int(self.DOSE * 10000)

    def filter_observation(self, obs, env_state):
        if not self._masked(env_state):
            return obs
        text = obs.text
        cut = text.find("\n\nAdmissible commands: ")
        if cut >= 0:
            text = text[:cut]
        data = dict(obs.data or {})
        data.pop("admissible_commands", None)
        return Observation(text=text, data=data)
```

### Gplus task 5 (candidate 2fd2db6d; accepted at 3/5 in search)

Setup actions: none

```python
class _Rules(Rules):
    """HorizonSqueeze (T axis): terminate the episode early if the agent doesn't succeed
    within 25 steps. This encourages more efficient navigation and planning."""

    def modify_transition(self, action, raw_response, env_state):
        if raw_response.info.get("won") is True or bool(getattr(env_state, "won", False)):
            return raw_response
        if raw_response.terminated or raw_response.truncated:
            return raw_response

        # Truncate at 25 steps
        if int(getattr(env_state, "step_count", 0) or 0) >= 25:
            return EnvResponse(
                observation=raw_response.observation,
                reward=raw_response.reward,
                terminated=False,
                truncated=True,
                info={**raw_response.info},
            )
        return raw_response
```

### Gplus task 8 (candidate e41dad70; accepted at 3/5 in search)

Setup actions: ['go to shelf 2', 'take soapbar 1 from shelf 2', 'go to garbagecan 1', 'put soapbar 1 in garbagecan 1']

```python
import hashlib

class _Rules(Rules):
    """FooterMask (O axis): hide the admissible-commands footer at 80% of steps."""
    DOSE = 0.8
    TASK_ID = "9e4d338c"

    def _masked(self, env_state):
        step = int(getattr(env_state, "step_count", 0) or 0)
        # Use a stable hash to determine if we mask this step
        digest = hashlib.sha256(f"{self.TASK_ID}:{step}".encode("utf-8")).hexdigest()
        return (int(digest[:8], 16) % 10000) < int(self.DOSE * 10000)

    def filter_observation(self, obs, env_state):
        if not self._masked(env_state):
            return obs

        text = obs.text
        # Cut off the admissible commands footer
        cut = text.find("\n\nAdmissible commands: ")
        if cut >= 0:
            text = text[:cut]

        # Remove the key from data as well
        new_data = dict(obs.data or {})
        new_data.pop("admissible_commands", None)

        return Observation(text=text, data=new_data)
```

### Gplus task 10 (candidate 5013a779; accepted at 2/5 in search)

Setup actions: none

```python
import hashlib

class _Rules(Rules):
    """
    Combined O-axis (FooterMask) and T-axis (HorizonSqueeze).
    Masks commands at 50% frequency and truncates episodes at 14 steps.
    """
    DOSE_MASK = 0.50
    M_STEPS = 14

    def _masked(self, env_state):
        step = int(getattr(env_state, "step_count", 0) or 0)
        task_id_hash = hashlib.md5(env_state.goal_text.encode("utf-8")).hexdigest()
        digest = hashlib.md5(f"{task_id_hash}:{step}".encode("utf-8")).hexdigest()
        return (int(digest[:8], 16) % 10000) < int(self.DOSE_MASK * 10000)

    def filter_observation(self, obs, env_state):
        if not self._masked(env_state):
            return obs

        text = obs.text
        cut = text.find("\n\nAdmissible commands: ")
        if cut >= 0:
            text = text[:cut]

        new_data = dict(obs.data or {})
        new_data.pop("admissible_commands", None)

        return Observation(text=text, data=new_data)

    def modify_transition(self, action, raw_response, env_state):
        # Allow success
        if raw_response.info.get("won") is True or bool(getattr(env_state, "won", False)):
            return raw_response
        if raw_response.terminated or raw_response.truncated:
            return raw_response

        # Squeeze horizon
        if int(getattr(env_state, "step_count", 0) or 0) >= self.M_STEPS:
            return EnvResponse(
                observation=raw_response.observation,
                reward=raw_response.reward,
                terminated=False,
                truncated=True,
                info={**raw_response.info, "horizon_squeeze": self.M_STEPS},
            )
        return raw_response
```

### Gplus task 14 (candidate 4ef49c8b; accepted at 3/5 in search)

Setup actions: ['go to dresser 1', 'open drawer 1', 'close drawer 1', 'go to bed 1']

```python
# (no rules code)
```

### Gplus task 27 (candidate c8a782fa; accepted at 2/5 in search)

Setup actions: none

```python
import hashlib

class _Rules(Rules):
    """FooterMask (O axis): hides the admissible-commands footer at 20% of steps.
    Forces the policy to rely on memory and environment exploration."""

    DOSE = 0.2
    TASK_ID = "8cd83e26"

    def _masked(self, env_state):
        step = int(getattr(env_state, "step_count", 0) or 0)
        digest = hashlib.sha256(f"{self.TASK_ID}:{step}".encode("utf-8")).hexdigest()
        return (int(digest[:8], 16) % 10000) < int(self.DOSE * 10000)

    def filter_observation(self, obs, env_state):
        if not self._masked(env_state):
            return obs
        text = obs.text
        cut = text.find("\n\nAdmissible commands: ")
        if cut >= 0:
            text = text[:cut]
        data = dict(obs.data or {})
        data.pop("admissible_commands", None)
        return Observation(text=text, data=data)
```
