"""F5: the Flash probe config must differ from corpus_eobs.yaml ONLY in the policy model id."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import yaml
from tests.test_configs import _diff
from eobs.settings import EOBS_ROOT


def test_flash_config_only_policy_model_differs():
    base = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs.yaml").read_text())
    fl = yaml.safe_load((EOBS_ROOT / "followup/corpus_eobs_flash.yaml").read_text())
    assert _diff(base, fl) == ["policy.client_kwargs"]
    b, f = base["policy"]["client_kwargs"], fl["policy"]["client_kwargs"]
    assert {k for k in set(b) | set(f) if b.get(k) != f.get(k)} == {"inner_kwargs"}
    bi, fi = b["inner_kwargs"], f["inner_kwargs"]
    assert {k for k in set(bi) | set(fi) if bi.get(k) != fi.get(k)} == {"model"} and fi["model"] == "openai/deepseek-v4-flash"
    assert fl["agent"] == base["agent"]
