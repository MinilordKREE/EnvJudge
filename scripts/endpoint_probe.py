"""One cheap ledgered call to the E2 policy endpoint (Qwen3-8B, Alibaba pin): exit 0 if it answers,
1 on a rate limit / infrastructure error. Used by the E2 chain to wait out an upstream throttle."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2_step1 as e2
from round1 import PRICING

from aea.core.config import RetryConfig
from aea.errors import InfraError
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.settings import load_settings


def main() -> int:
    policy, _ = e2.backbone_e2()
    policy = policy.model_copy(update={"retry": RetryConfig(max_attempts=1), "max_tokens": 8})
    out = e2.RUNS / "e2-probe"
    out.mkdir(parents=True, exist_ok=True)
    key = load_settings().require(policy.api_key_env.lower())
    client = OpenAICompatibleClient(
        config=policy,
        transport=make_openai_transport(api_key=key, base_url=policy.base_url, timeout_s=60.0),
        ledger=Ledger(out / "ledger.jsonl", "e2-probe"),
        pricing=load_pricing(PRICING),
    )
    req = ChatRequest(
        model=policy.model,
        messages=(ChatMessage(role="user", content="Reply with the single word OK."),),
        max_tokens=8,
        attribution=Attribution(phase="endpoint_probe", budget="none", arm="infra", task_id="e2"),
    )
    try:
        resp = client.complete(req)
    except InfraError as exc:
        print(f"PROBE_FAIL {exc.kind}")
        return 1
    print(f"PROBE_OK provider={resp.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
