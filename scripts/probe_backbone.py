"""Phase 0b step 1: backbone price/caching probe on OpenRouter (calls with a long shared prefix).

Reports per call: provider, prompt/cached/completion tokens, upstream ``usage.cost``, the table
price and the residual, then the cache-write rate that would explain each residual. No table
change is made here: the owner's rule decides (add a single rate and re-verify, or stop).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from aea.core.config import LLMConfig
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
PREFIX_UNIT = (
    "You are an agent in a text-based household environment (ALFWorld). " * 8
    + "Observation: You see a cabinet 1, a countertop 2, a fridge 1, a sinkbasin 1, a microwave 1. "
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/gemini-3.1-flash-lite")
    ap.add_argument("--pin", default="google-ai-studio")
    ap.add_argument("--calls", type=int, default=5)
    ap.add_argument("--prefix-units", type=int, default=50)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "probe_backbone.jsonl")
    args = ap.parse_args(argv)
    cfg = LLMConfig(
        provider="openrouter",
        model=args.model,
        provider_pin=args.pin,
        thinking=None,
        temperature=0.0,
        max_tokens=64,
        cost_tolerance=1e9,
    )
    key = load_settings().require("openrouter_api_key")
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    ledger = Ledger(args.out.with_suffix(".ledger.jsonl"), "probe-backbone")
    transport = make_openai_transport(api_key=key, base_url=cfg.base_url, timeout_s=120)
    client = OpenAICompatibleClient(config=cfg, transport=transport, ledger=ledger, pricing=pricing)
    prefix = PREFIX_UNIT * max(1, args.prefix_units)
    rows: list[dict[str, object]] = []
    for i in range(args.calls):
        req = ChatRequest(
            model=cfg.model,
            messages=(
                ChatMessage(role="system", content=prefix),
                ChatMessage(role="user", content=f"Turn {i}: reply with the single word OK."),
            ),
            temperature=0.0,
            max_tokens=64,
            attribution=Attribution(phase="probe", budget="none", arm="probe", task_id="probe"),
        )
        r = client.complete(req)
        table = pricing.cost(cfg.model, r.usage, r.created_at).usd
        residual = (r.upstream_cost - table) if r.upstream_cost is not None else None
        uncached = r.usage.prompt_tokens - r.usage.cached_tokens
        row: dict[str, object] = {
            "i": i,
            "provider": r.provider,
            "prompt_tokens": r.usage.prompt_tokens,
            "cached_tokens": r.usage.cached_tokens,
            "completion_tokens": r.usage.completion_tokens,
            "reasoning_tokens": r.usage.reasoning_tokens,
            "upstream_cost": r.upstream_cost,
            "table_usd": table,
            "residual": residual,
            "implied_cache_write_per_M": (residual / uncached * 1e6)
            if (residual is not None and uncached)
            else None,
            "content": r.content[:40],
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    rates = pricing.pricing_for(cfg.model).rates_at(datetime.now(UTC))[1]
    print(json.dumps({"table_rates": rates.model_dump()}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
