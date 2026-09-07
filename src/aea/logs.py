"""Structured logging: stdlib ``logging`` with a JSON-lines formatter.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/logs.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename only.

Library code obtains loggers with ``logging.getLogger(__name__)`` and never prints.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

PACKAGE_LOGGER = "aea"

_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
    | {"message", "asctime", "taskName"}
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg, extra fields, and exc if present."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _AeaHandlerMarker:
    """Mixin used to recognise handlers installed by :func:`configure_logging`."""


class _ConsoleHandler(logging.StreamHandler[TextIO], _AeaHandlerMarker):
    pass


class _JsonFileHandler(logging.FileHandler, _AeaHandlerMarker):
    pass


def configure_logging(
    *,
    level: int = logging.INFO,
    json_path: Path | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Install a console handler and, if ``json_path`` is given, a JSON-lines file handler.

    Idempotent: previously installed aea handlers are removed first. Only the ``aea`` logger
    tree is configured; the root logger is left alone.
    """
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        if isinstance(handler, _AeaHandlerMarker):
            logger.removeHandler(handler)
            handler.close()

    console = _ConsoleHandler(stream or sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(console)

    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = _JsonFileHandler(json_path, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    return logger
