"""F_H — horizon squeeze (T-axis): terminate the episode with failure at step m via modify_transition.

`env_state.step_count` (post-step) counts actions taken; when it reaches m and the task is not won, the transition is
rewritten as terminated (success stays False because the bridge's evaluate() reads `won`). Certified by construction
when the shortest certified expert plan length L_exp ≤ m (PREREG3b)."""

TEMPLATE = '''
class _Rules(Rules):
    M = {m}

    def modify_transition(self, action, raw_response, env_state):
        sc = int(getattr(env_state, "step_count", 0) or 0)
        won = bool(getattr(env_state, "won", False))
        if sc >= self.M and not won and not raw_response.terminated:
            return EnvResponse(observation=raw_response.observation, reward=raw_response.reward, terminated=True,
                               truncated=raw_response.truncated, info={{**raw_response.info, "horizon_squeeze": self.M}})
        return raw_response
'''


def rules_code(m: int) -> str:
    return TEMPLATE.format(m=int(m)).strip() + "\n"
