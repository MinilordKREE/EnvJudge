"""Exemplar knobs: the single source of truth for the few-shot prompt text and the runnable classes.

Spec: docs/spec/AEA_v2.md section 3 (FooterMask, HorizonSqueeze, Displacement). The templates are
stored
verbatim (``*.py.txt``) with ``__DOSE__`` / ``__TASK_ID__`` / ``__M__`` placeholders; ``render``
substitutes them for a runnable ``rules_code`` and ``prompt_text`` returns the same text unfilled
for the proposer. They use only the names the released ``code_loader`` provides
(``envharness/core/code_loader.py:54-66``) plus standard-library imports made inside the string.
"""

from __future__ import annotations

from importlib import resources

_FILES = {"footer_mask": "footer_mask.py.txt", "horizon_squeeze": "horizon_squeeze.py.txt"}


def _read(name: str) -> str:
    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")


def prompt_text(name: str) -> str:
    """The exemplar exactly as shown to the proposer (placeholders left in place)."""
    if name == "displacement":
        return _read("displacement.md")
    return _read(_FILES[name])


def render(name: str, **params: object) -> str:
    """Runnable rules code: ``__KEY__`` placeholders replaced by ``repr(value)``."""
    text = _read(_FILES[name])
    for key, value in params.items():
        text = text.replace(f"__{key.upper()}__", repr(value))
    if "__" in text and any(f"__{k}__" in text for k in ("DOSE", "TASK_ID", "M")):
        missing = [k for k in ("DOSE", "TASK_ID", "M") if f"__{k}__" in text]
        raise ValueError(f"exemplar {name}: unfilled placeholders {missing}")
    return text
