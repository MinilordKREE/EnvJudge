# ruff: noqa
import math
import re


class _Rules(Rules):
    """Oracle actuator, class S (explored-receptacle pruning): while the goal object is not in
    hand, `go to R` is removed from the admissible commands for receptacles R whose contents the
    policy has ALREADY SEEN without the goal object. Dose = fraction of those receptacles
    pruned (earliest inspected first). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    OBJ = 'tomato'  # goal object type, from the goal text

    def _mem(self, env_state):
        ex = getattr(env_state, "extras", None)
        if not isinstance(ex, dict):
            ex = self.__dict__.setdefault("_oracle_extras", {})
        return ex.setdefault("oracle_S", {"inspected": [], "held": False})

    @staticmethod
    def _body(text):
        return text.split("\n\nAdmissible commands:")[0]

    @staticmethod
    def _covered(k, dose):
        return math.floor(k * dose + 1e-9) > math.floor((k - 1) * dose + 1e-9)

    def _update(self, text, mem):
        if "Welcome to TextWorld" in text:
            mem["inspected"] = []
            mem["held"] = False
        body = self._body(text)
        if re.search(r"You pick up the %s \d+" % self.OBJ, body):
            mem["held"] = True
        elif re.search(r"You move the %s \d+ to" % self.OBJ, body):
            mem["held"] = False
        elif "You are carrying: " in body:
            mem["held"] = bool(re.search(r"\b%s \d+" % self.OBJ, body))
        elif "You are not carrying anything" in body:
            mem["held"] = False
        m = re.search(r"(?:You arrive at|You open the) ([a-z]+ \d+)\.", body)
        if m and ", you see " in body:
            recep = m.group(1)
            listing = body.split(", you see ", 1)[1]
            if not re.search(r"\b%s \d+" % self.OBJ, listing) and recep not in mem["inspected"]:
                mem["inspected"].append(recep)

    def filter_observation(self, obs, env_state):
        mem = self._mem(env_state)
        self._update(obs.text, mem)
        if self.DOSE <= 0 or mem["held"]:
            return obs
        k = int(self.DOSE * len(mem["inspected"]) + 1e-9)
        pruned = set(mem["inspected"][:k])
        if not pruned:
            return obs
        cmds = list((obs.data or {}).get("admissible_commands") or [])
        kept = [c for c in cmds if not (c.startswith("go to ") and c[6:] in pruned)]
        if kept == cmds:
            return obs
        text = self._body(obs.text) + "\n\nAdmissible commands: " + ", ".join(kept)
        data = dict(obs.data or {})
        data["admissible_commands"] = kept
        return Observation(text=text, data=data)
