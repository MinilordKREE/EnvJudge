"""Environment-side Contracts. Pure functions; none of them touches comparison logic.

c1  unwrap_fence(text) -> code
    Tolerant extraction of the program from a chat response. Order of preference: the first
    fenced block whose info string starts with "py" (python, py, python3, Python ...), else the
    first fenced block with an empty info string, else the whole response. Fences are ``` runs
    (3+ backticks) or ~~~ runs. The substrate's own extractor only accepts an info string that
    is exactly `python`/`py` and otherwise treats the whole response as code, which fails on
    `python3`, untagged fences, or prose around the fence. Bug fixed 2026-09-05 09:20 UTC after the arms
    ran: the first version anchored the opening fence to line start and therefore fell back to the whole
    response for fences written inline after prose (see LOG.md; affected rollouts were re-processed).

c2  run_with_save_on_exception(code, output_path) -> code
    Source-level wrapper around the generated program. The wrapped program behaves identically
    when it runs to completion. If it raises (any BaseException, including SystemExit), the
    handler scans the exec namespace -- every frame on the exception traceback (f_locals,
    outermost to innermost) and then module globals() -- for openpyxl Workbook instances and,
    if OUTPUT_PATH does not exist yet, saves the innermost / most recently seen Workbook to
    OUTPUT_PATH, prints a marker to stderr, and re-raises. The runner therefore still reports a
    non-zero exit; only the artifact is preserved. The wrapper uses no dunder attributes and no
    forbidden imports, so the substrate's isolation validator accepts it unchanged.

c3  recalc(path, soffice, timeout) -> (ok, detail)
    The official SpreadsheetBench Online-Judge recalculation step (open_spreadsheet.py):
    LibreOffice Calc headless converts the workbook to xlsx in a temp dir (formulas are
    recalculated and cached) and the result replaces the file in place. Mirrors the vendored
    `recalc_with_libreoffice` command line exactly, except that the user profile is a fresh
    temp dir per call (the vendored one is per pid, which is unsafe under threads).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap

# Opening fence may sit anywhere (also inline after prose, as the substrate regex allows); the info
# string is the rest of that line; the closing fence is the next run of the same fence characters.
_FENCE = re.compile(
    r"(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*)\n(?P<code>.*?)(?P=fence)",
    re.DOTALL,
)


def unwrap_fence(text: str) -> str:
    """c1: return the program text (see module docstring). Raises ValueError if empty."""
    blocks = [(m.group("info").strip().lower(), m.group("code")) for m in _FENCE.finditer(text or "")]
    code = None
    for info, body in blocks:
        if info.split()[:1] and info.split()[0].startswith("py"):
            code = body
            break
    if code is None:
        for info, body in blocks:
            if info == "":
                code = body
                break
    if code is None:
        code = text or ""
    code = textwrap.dedent(code).strip("\n").strip()
    if not code:
        raise ValueError("no_code_in_response")
    return code


_C2_HEAD = "import sys as _emin_sys, os as _emin_os\ntry:\n"
_C2_TAIL = textwrap.dedent(
    """
    except BaseException as _emin_exc:
        try:
            import openpyxl as _emin_openpyxl
            _emin_cands = []
            _emin_tb = _emin_sys.exc_info()[2]
            while _emin_tb is not None:
                for _emin_v in list(_emin_tb.tb_frame.f_locals.values()):
                    if isinstance(_emin_v, _emin_openpyxl.Workbook):
                        _emin_cands.append(_emin_v)
                _emin_tb = _emin_tb.tb_next
            for _emin_v in list(globals().values()):
                if isinstance(_emin_v, _emin_openpyxl.Workbook):
                    _emin_cands.append(_emin_v)
            if _emin_cands and not _emin_os.path.exists(OUTPUT_PATH):
                _emin_cands[-1].save(OUTPUT_PATH)
                _emin_sys.stderr.write("EMIN_C2_SAVED_ON_EXCEPTION\\n")
        except BaseException:
            pass
        raise
    """
).strip("\n") + "\n"

C2_MARKER = "EMIN_C2_SAVED_ON_EXCEPTION"


def run_with_save_on_exception(code: str, output_path: str = "OUTPUT_PATH") -> str:
    """c2: wrap `code` so a Workbook in the namespace is saved to OUTPUT_PATH on exception.

    `output_path` is the *expression* used for the destination (default: the runner-provided
    `OUTPUT_PATH` name). `from __future__` imports are hoisted above the wrapper.
    """
    lines = code.splitlines()
    future = [ln for ln in lines if ln.strip().startswith("from __future__ import")]
    body = [ln for ln in lines if not ln.strip().startswith("from __future__ import")]
    body_text = "\n".join(body).strip("\n") or "pass"
    tail = _C2_TAIL if output_path == "OUTPUT_PATH" else _C2_TAIL.replace("OUTPUT_PATH", output_path)
    return "".join(f"{ln}\n" for ln in future) + _C2_HEAD + textwrap.indent(body_text, "    ") + "\n" + tail


_PROFILE_ROOT = os.path.join(tempfile.gettempdir(), "emin_lo_profiles")


def _thread_profile() -> str:
    """One LibreOffice user profile per (process, thread): never shared concurrently (the headless
    concurrency trap), but reused across calls so the multi-second first-start profile
    initialisation is paid once per worker instead of once per conversion."""
    import threading

    d = os.path.join(_PROFILE_ROOT, f"{os.getpid()}_{threading.get_ident()}")
    os.makedirs(d, exist_ok=True)
    return d


def recalc(path: str, soffice: str, timeout: int = 120) -> tuple[bool, str]:
    """c3: recalculate `path` in place with headless LibreOffice. Returns (ok, detail)."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return False, "missing_input"
    if not (soffice and os.path.isfile(soffice)):
        return False, "soffice_not_found"
    name = os.path.splitext(os.path.basename(path))[0]
    profile = _thread_profile()
    with tempfile.TemporaryDirectory(prefix="emin_lo_out_") as out:
        env = dict(os.environ)
        env.setdefault("HOME", profile)
        cmd = [
            soffice,
            "-env:UserInstallation=file://" + profile,
            "--headless",
            "--calc",
            "--convert-to",
            "xlsx:Calc MS Excel 2007 XML",
            "--outdir",
            out,
            path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        if r.returncode != 0:
            return False, f"exit_{r.returncode}:{(r.stderr or r.stdout)[-300:]}"
        converted = os.path.join(out, name + ".xlsx")
        if not os.path.isfile(converted):
            return False, "no_output:" + (r.stderr or r.stdout)[-300:]
        shutil.move(converted, path)
        return True, "ok"
