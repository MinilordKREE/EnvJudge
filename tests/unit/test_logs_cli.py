from __future__ import annotations

import json
import logging
from pathlib import Path

from aea import __version__
from aea.cli import main
from aea.logs import configure_logging


def test_json_log_handler(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    logger = configure_logging(json_path=path)
    logging.getLogger("aea.test").info("hi", extra={"task_id": "7"})
    logger.handlers[0].flush()
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["msg"] == "hi" and record["task_id"] == "7" and record["level"] == "INFO"
    configure_logging(json_path=path)  # idempotent


def test_cli(capsys: object, tmp_path: Path) -> None:
    assert main(["version"]) == 0
    cfg = tmp_path / "run.yaml"
    cfg.write_text("schema_version: 1\nname: x\n", encoding="utf-8")
    assert main(["config-hash", str(cfg)]) == 0
    cfg.write_text("schema_version: 1\nname: x\nbogus: 1\n", encoding="utf-8")
    assert main(["config-hash", str(cfg)]) == 2
    assert main(["ledger", str(tmp_path / "missing.jsonl")]) == 3
    assert __version__
