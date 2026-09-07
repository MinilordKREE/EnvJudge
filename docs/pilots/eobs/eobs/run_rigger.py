"""Launcher: load secrets via pydantic-settings, export what litellm needs, run the released run_harness.py.

Usage: python -m eobs.run_rigger --run-name eobs_alfworld_001 --n-tasks N --task-offset 0 [--config configs/corpus_eobs.yaml]
The YAML never carries the key; OPENAI_API_KEY is set only in this process's environment (litellm's openai
provider reads it for the OpenAI-compatible DeepSeek endpoint). PYTHONPATH gets scratch/eobs so episode
subprocesses can import eobs.llm.
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

from eobs.settings import ENVHARNESS_ROOT, EOBS_ROOT, secrets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(EOBS_ROOT / "configs" / "corpus_eobs.yaml"))
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--n-tasks", type=int, required=True)
    ap.add_argument("--task-offset", type=int, default=0)
    ap.add_argument("--phase", default="phase2")
    a = ap.parse_args()
    os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["EOBS_RUN_ID"] = a.run_name
    os.environ["EOBS_PHASE"] = a.phase
    os.environ["PYTHONPATH"] = str(EOBS_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    script = ENVHARNESS_ROOT / "scripts" / "run_harness.py"
    sys.argv = [str(script), "--config", a.config, "--run-name", a.run_name, "--n-tasks", str(a.n_tasks),
                "--task-offset", str(a.task_offset)]
    os.chdir(ENVHARNESS_ROOT)   # run_harness resolves ./runs relative to cwd for the scripted path; configs use absolute paths
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
