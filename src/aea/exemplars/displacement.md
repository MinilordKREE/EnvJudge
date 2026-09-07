Displacement (S0 axis, harder with DOSE; DOSE in {1/3, 2/3, 1} maps to k in {1, 2, 3}): the target
objects the expert picks up are moved before the policy starts. k=1: each target to a different open
receptacle (not its source, never the goal receptacle class); k=2: each target inside a closable
container (go to C, open C, move, close C); k=3: k=2 plus every other closable container closed. The
action list is validated step by step (admissible before issue, effective after) and ends with
`look`; it is a Setup action list (`in_env_actions`), not rules code. Certified by the expert x3
from the staged state.
