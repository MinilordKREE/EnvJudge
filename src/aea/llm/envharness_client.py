"""envharness ``LLMClient`` adapter: routes the substrate's policy / designer calls through aea.

Reference (wrapped, not copied): third_party/envharness ``envharness/infra/llm.py`` --
``LLMClient`` ABC (``chat(messages, tools, tool_choice, temperature, max_tokens, **kwargs)``),
``Message`` / ``ToolCall`` / ``ChatResponse`` dataclasses (lines 20-44), ``LoggingLLMClient``
(the released wrap-any-client pattern). The pilot oracle is docs/pilots/eobs/eobs/llm.py
(``LedgerLLMClient``), rewritten here on top of :class:`aea.llm.client.OpenAICompatibleClient`.
No reference source copied.

The orchestrator instantiates clients through ``client_factory`` + ``client_kwargs`` (subprocess
runners included), so the adapter builds its own client from a serialisable ``LLMConfig`` dict
and a ledger directory; the attribution comes from :mod:`aea.llm.attribution` (a contextvar in the
parent, the ``AEA_*`` variables exported by :class:`aea.runner.AeaSubprocessRunner` in a worker).
Each process appends to its own ``ledger.<pid>.jsonl`` (merged by ``aea.runner.merge_ledgers``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from envharness.infra.llm import ChatResponse as EHChatResponse
from envharness.infra.llm import LLMClient, Message, ToolCall

from aea.core.config import LLMConfig
from aea.llm.attribution import current_attribution
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import ChatMessage, ChatRequest, ChatResponse
from aea.llm.types import ToolCall as AeaToolCall
from aea.settings import load_settings


class AeaLLMClient(LLMClient):  # type: ignore[misc]  # envharness ships no type information
    """Drop-in ``client_factory`` for envharness configs; every call becomes a ledger row."""

    def __init__(
        self, *, llm: dict[str, Any], ledger_dir: str, pricing_path: str = "configs/pricing.yaml"
    ) -> None:
        self.config = LLMConfig.model_validate(llm)
        self.model_id = self.config.model
        settings = load_settings()
        key = settings.require(self.config.api_key_env.lower())
        transport = make_openai_transport(
            api_key=key, base_url=self.config.base_url, timeout_s=self.config.timeout_s
        )
        run_id = os.environ.get("AEA_RUN_ID", "unset")
        ledger_path = Path(ledger_dir) / f"ledger.{os.getpid()}.jsonl"
        self._client = OpenAICompatibleClient(
            config=self.config,
            transport=transport,
            ledger=Ledger(ledger_path, run_id),
            pricing=load_pricing(Path(pricing_path)),
        )

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> EHChatResponse:
        attribution, seed = current_attribution()
        request = ChatRequest(
            model=self.config.model,
            messages=tuple(
                ChatMessage(
                    role=cast(Any, m.role),
                    content=m.content or "",
                    name=m.name,
                    tool_call_id=m.tool_call_id,
                    tool_calls=tuple(
                        AeaToolCall(id=t.id, name=t.name, arguments=dict(t.arguments))
                        for t in (m.tool_calls or [])
                    )
                    or None,
                )
                for m in messages
            ),
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens or self.config.max_tokens,
            thinking=self.config.thinking,
            reasoning_effort=self.config.reasoning_effort,
            timeout_s=self.config.timeout_s,
            attribution=attribution,
            tools=tuple(tools) if tools else None,
            tool_choice=tool_choice if tools else None,
        )
        response: ChatResponse = self._client.complete(request)
        return EHChatResponse(
            content=response.content,
            tool_calls=[
                ToolCall(id=t.id, name=t.name, arguments=dict(t.arguments))
                for t in response.tool_calls
            ],
            raw=response,
        )
