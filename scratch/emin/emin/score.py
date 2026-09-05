"""Both scoring paths for one output workbook. Never modifies either verifier.

substrate path : rethinkskill.benchmarks.scoring.verify_spreadsheet (data_only=True, NO recalc)
official  path : vendored envharness online_judge_eval.compare_workbooks after LibreOffice recalc
                 of BOTH the agent output (copy) and the golden (copy, cached per golden file)

Reason vocabulary (fixed): pass | value_mismatch | sheet_missing | workbook_missing |
workbook_parse_error | recalc_error | answer_position_parse_error
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from emin.contracts import recalc
from emin.settings import config, ensure_pilot_importable

ensure_pilot_importable()

from rethinkskill.benchmarks.scoring import Verdict, verify_spreadsheet  # noqa: E402

from emin.third_party.online_judge_eval import compare_workbooks  # noqa: E402

REASONS = (
    "pass",
    "value_mismatch",
    "sheet_missing",
    "workbook_missing",
    "workbook_parse_error",
    "recalc_error",
    "answer_position_parse_error",
)


@dataclass(frozen=True)
class Score:
    verdict: str          # "PASS" | "FAIL"
    reason: str           # one of REASONS
    detail: str = ""      # verifier's own message (free text)

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def to_dict(self) -> dict:
        return asdict(self)


def _map_substrate_reason(verdict: Verdict, reason: str) -> str:
    if verdict is Verdict.PASS:
        return "pass"
    head = reason.split(":", 1)[0]
    if head in ("value_mismatch", "sheet_missing", "workbook_missing", "workbook_parse_error"):
        return head
    if head in ("answer_position_empty_or_unparseable",):
        return "answer_position_parse_error"
    return "workbook_parse_error" if verdict is Verdict.FAIL else "answer_position_parse_error"


def score_substrate(output: Path, golden: Path, answer_position: str) -> Score:
    try:
        v = verify_spreadsheet(Path(output), Path(golden), answer_position)
    except Exception as exc:  # range_boundaries etc. raise through the verifier
        return Score("FAIL", "answer_position_parse_error", f"{type(exc).__name__}: {exc}"[:300])
    if v.verdict is Verdict.ABSTAIN:
        return Score("FAIL", "answer_position_parse_error", v.reason)
    return Score("PASS" if v.verdict is Verdict.PASS else "FAIL", _map_substrate_reason(v.verdict, v.reason), v.reason)


def _map_official_msg(msg: str) -> str:
    if msg.startswith("output file does not exist"):
        return "workbook_missing"
    if msg.startswith("load error"):
        return "workbook_parse_error"
    if "worksheet not found" in msg:
        return "sheet_missing"
    if "value diff" in msg:
        return "value_mismatch"
    return "value_mismatch"


def compare_official(golden_recalced: Path, output_recalced: Path, answer_position: str, instruction_type: str = "") -> Score:
    """Official cell comparison on two already-recalculated workbooks."""
    try:
        ok, msg = compare_workbooks(str(golden_recalced), str(output_recalced), instruction_type, answer_position)
    except Exception as exc:  # malformed answer_position -> _parse_cell_range raises
        return Score("FAIL", "answer_position_parse_error", f"{type(exc).__name__}: {exc}"[:300])
    if ok:
        return Score("PASS", "pass", msg)
    return Score("FAIL", _map_official_msg(msg), msg[:300])


_GOLDEN_LOCKS: dict[str, threading.Lock] = {}
_GOLDEN_LOCKS_GUARD = threading.Lock()


def golden_recalced(golden: Path, cache_dir: Path, soffice: str | None = None, timeout: int | None = None) -> tuple[Path | None, str]:
    """Recalculated copy of a golden workbook, cached by content hash (deterministic step; not a rollout cache)."""
    cfg = config()
    soffice = soffice or cfg["soffice"]
    timeout = timeout or cfg["execution"]["recalc_timeout_seconds"]
    digest = hashlib.sha256(Path(golden).read_bytes()).hexdigest()[:24]
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{digest}.xlsx"
    marker = cache_dir / f"{digest}.status"
    with _GOLDEN_LOCKS_GUARD:
        lock = _GOLDEN_LOCKS.setdefault(digest, threading.Lock())
    with lock:
        if marker.exists():
            status = marker.read_text(encoding="utf-8").strip()
            return (target if status == "ok" and target.exists() else None), status
        # several arm processes share this cache: process/thread-unique temp name, tolerate a concurrent winner
        tmp = cache_dir / f"{digest}.{os.getpid()}.{threading.get_ident()}.tmp.xlsx"
        shutil.copyfile(golden, tmp)
        ok, detail = recalc(str(tmp), soffice, timeout)
        if ok:
            if target.exists():
                tmp.unlink(missing_ok=True)
            else:
                try:
                    os.replace(tmp, target)
                except FileNotFoundError:
                    pass
            marker.write_text("ok", encoding="utf-8")
            return target, "ok"
        tmp.unlink(missing_ok=True)
        marker.write_text(f"recalc_error:{detail}", encoding="utf-8")
        return None, f"recalc_error:{detail}"


def score_official(output: Path, golden: Path, answer_position: str, instruction_type: str, work_dir: Path,
                   soffice: str | None = None, timeout: int | None = None) -> Score:
    """Official OJ path: recalc a copy of the output and (cached) golden, then compare_workbooks."""
    cfg = config()
    soffice = soffice or cfg["soffice"]
    timeout = timeout or cfg["execution"]["recalc_timeout_seconds"]
    output = Path(output)
    if not output.is_file():
        return Score("FAIL", "workbook_missing", "output file does not exist")
    g, status = golden_recalced(Path(golden), Path(work_dir) / "golden_recalc", soffice, timeout)
    if g is None:
        return Score("FAIL", "recalc_error", f"golden:{status}"[:300])
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    copy = output.with_name(output.stem + ".recalc.xlsx")
    shutil.copyfile(output, copy)
    ok, detail = recalc(str(copy), soffice, timeout)
    if not ok:
        return Score("FAIL", "recalc_error", f"output:{detail}"[:300])
    return compare_official(g, copy, answer_position, instruction_type)


def score_both(output: Path, golden: Path, answer_position: str, instruction_type: str, work_dir: Path) -> dict:
    """{'substrate': Score, 'official': Score} for one output workbook."""
    return {
        "substrate": score_substrate(output, golden, answer_position),
        "official": score_official(output, golden, answer_position, instruction_type, work_dir),
    }
