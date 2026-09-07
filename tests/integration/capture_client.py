"""An envharness ``LLMClient`` that records every prompt and answers with a scripted action."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from envharness.infra.llm import ChatResponse, LLMClient, Message


class CaptureClient(LLMClient):  # type: ignore[misc]  # envharness ships no type information
    """Appends every call's messages to the capture file; replies ``<action>look</action>``."""

    def __init__(self, action: str = "look", capture_path: str | None = None) -> None:
        self.model_id = "capture"
        self.action = action
        self.capture_path = Path(capture_path or os.environ["AEA_CAPTURE_PATH"])

    def chat(
        self,
        messages: list[Message],
        tools: Any = None,
        tool_choice: Any = "auto",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        with self.capture_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps([{"role": m.role, "content": m.content} for m in messages]) + "\n")
        return ChatResponse(content=f"<think>ok</think><action>{self.action}</action>")
