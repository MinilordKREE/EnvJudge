"""``aea`` command line: version, config hash, ledger summary.

No reference source: written fresh for aea (see docs/reuse/M0.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aea import __version__
from aea.core.config import config_sha256, load_run_config
from aea.errors import ConfigError, InfraError
from aea.llm.ledger import read_ledger, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aea")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the package version")
    cfg = sub.add_parser("config-hash", help="hash a run config after validation")
    cfg.add_argument("path", type=Path)
    led = sub.add_parser("ledger", help="summarise a ledger file")
    led.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "version":
            print(__version__)
        elif args.command == "config-hash":
            print(config_sha256(load_run_config(args.path)))
        elif args.command == "ledger":
            print(summarize(read_ledger(args.path)).model_dump_json(indent=2))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except InfraError as exc:
        print(f"infra error: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
