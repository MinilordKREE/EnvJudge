# ruff: noqa
import math


class _Rules(Rules):
    """Oracle actuator, class G (goal-decomposition annotation): the observation carries one
    line spelling the goal as its sub-steps in goal words. Dose = fraction of observations
    annotated (evenly, in order). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    LINE = 'Goal steps: (1) find a plate and take it; (2) heat it in the microwave; (3) put it on a countertop.'  # the goal decomposed, goal words + task-template knowledge

    def _mem(self, env_state):
        ex = getattr(env_state, "extras", None)
        if not isinstance(ex, dict):
            ex = self.__dict__.setdefault("_oracle_extras", {})
        return ex.setdefault("oracle_G", {"k": 0})

    @staticmethod
    def _body(text):
        return text.split("\n\nAdmissible commands:")[0]

    @staticmethod
    def _covered(k, dose):
        return math.floor(k * dose + 1e-9) > math.floor((k - 1) * dose + 1e-9)

    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        mem = self._mem(env_state)
        if "Welcome to TextWorld" in obs.text:
            mem["k"] = 0
        mem["k"] += 1
        if not self._covered(mem["k"], self.DOSE):
            return obs
        parts = obs.text.split("\n\nAdmissible commands:", 1)
        text = parts[0] + "\n\n" + self.LINE
        if len(parts) > 1:
            text += "\n\nAdmissible commands:" + parts[1]
        return Observation(text=text, data=dict(obs.data or {}))
