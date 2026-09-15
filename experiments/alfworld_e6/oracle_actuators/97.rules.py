# ruff: noqa
import math
import re


class _Rules(Rules):
    """Oracle actuator, class P (precondition gating): the goal-completing action is rejected
    with a reason in goal words while its goal precondition does not hold (the goal object is
    not in hand / not yet in the required state). Dose = fraction of premature attempts
    blocked (evenly, in order). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    OBJ = 'potato'  # goal object type, from the goal text
    COMPLETE = '^move potato \\d+ to garbagecan \\d+$'  # goal-completing action pattern, from the goal text
    PRECOND = 'cleaned'  # "held" or "cleaned"
    REASON = 'The goal needs a CLEAN potato: clean it (at the sinkbasin) before putting it in the garbagecan.'

    def _mem(self, env_state):
        ex = getattr(env_state, "extras", None)
        if not isinstance(ex, dict):
            ex = self.__dict__.setdefault("_oracle_extras", {})
        return ex.setdefault("oracle_P", {"held": None, "cleaned": [], "attempts": 0})

    @staticmethod
    def _body(text):
        return text.split("\n\nAdmissible commands:")[0]

    @staticmethod
    def _covered(k, dose):
        return math.floor(k * dose + 1e-9) > math.floor((k - 1) * dose + 1e-9)

    def _update(self, text, mem):
        if "Welcome to TextWorld" in text:
            mem["held"] = None
            mem["cleaned"] = []
            mem["attempts"] = 0
        body = self._body(text)
        m = re.search(r"You pick up the (%s \d+)" % self.OBJ, body)
        if m:
            mem["held"] = m.group(1)
        elif re.search(r"You move the %s \d+ to" % self.OBJ, body):
            mem["held"] = None
        elif "You are carrying: " in body:
            c = re.search(r"\b(%s \d+)" % self.OBJ, body)
            mem["held"] = c.group(1) if c else None
        elif "You are not carrying anything" in body:
            mem["held"] = None
        c = re.search(r"You clean the (%s \d+) using" % self.OBJ, body)
        if c and c.group(1) not in mem["cleaned"]:
            mem["cleaned"].append(c.group(1))

    def _satisfied(self, mem, text):
        if self.PRECOND == "held":
            return mem["held"] is not None
        inst = re.search(r"\b(%s \d+)" % self.OBJ, text)
        return bool(inst) and inst.group(1) in mem["cleaned"]

    def filter_observation(self, obs, env_state):
        self._update(obs.text, self._mem(env_state))
        return obs

    def filter_action(self, action, env_state):
        if self.DOSE <= 0:
            return action
        text = str((action.kwargs or {}).get("text", "")).strip().lower()
        if not re.match(self.COMPLETE, text):
            return action
        mem = self._mem(env_state)
        if self._satisfied(mem, text):
            return action
        mem["attempts"] += 1
        if self._covered(mem["attempts"], self.DOSE):
            return Blocked(reason=self.REASON)
        return action
