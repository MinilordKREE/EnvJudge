import pathlib, yaml
from tests.test_configs import _diff   # eobs test helper
from eobs.settings import EOBS_ROOT

E1 = pathlib.Path(__file__).resolve().parents[1]


def test_qwen_map_differs_only_in_policy_client_and_paths():
    base = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs.yaml").read_text())
    q = yaml.safe_load((E1 / "configs/qwen_map.yaml").read_text())
    assert _diff(base, q) == ["agent.client_kwargs", "logging.log_dir", "policy.client_kwargs", "storage.trace_path"]
    pk = q["policy"]["client_kwargs"]
    assert pk["api_key_env"] == "DASHSCOPE_API_KEY" and pk["inner_kwargs"]["model"] == "openai/qwen3-8b"
    assert pk["inner_kwargs"]["extra_body"] == {"enable_thinking": False}
    assert pk["inner_kwargs"]["api_base"].startswith("https://dashscope") and pk["inner_kwargs"]["api_base"].endswith("/compatible-mode/v1")
    ak, bk = q["agent"]["client_kwargs"], base["agent"]["client_kwargs"]
    assert {k for k in set(ak) | set(bk) if ak.get(k) != bk.get(k)} == {"ledger_path", "api_key_env"} and ak["api_key_env"] == "DEEPSEEK_API_KEY"
    for k in ("policy", "agent"):
        assert q[k].get("temperature") == base[k].get("temperature") and q[k].get("task_description") == base[k].get("task_description")
    assert q["orchestrator"] == base["orchestrator"] and q["objective"] == base["objective"] and q["budget"] == base["budget"] and q["env"] == base["env"]
