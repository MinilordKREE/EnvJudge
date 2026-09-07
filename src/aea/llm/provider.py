"""The one interface every model backend implements.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/provider.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aea.llm.types import ChatRequest, ChatResponse


@runtime_checkable
class Provider(Protocol):
    def complete(self, request: ChatRequest) -> ChatResponse:
        """Return a completion. Infra problems raise ``InfraError``; never return a fake answer."""
        ...
