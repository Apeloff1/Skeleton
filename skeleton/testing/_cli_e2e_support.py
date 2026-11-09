"""Shared helpers for the developer CLI end-to-end suites (test_cli_e2e_*)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_inprocess(argv: List[str]) -> Tuple[Any, str, str, Optional[int]]:
    """Run ``run_dev_cli`` in-process.

    Returns (result, stdout, stderr, system_exit_code). ``system_exit_code`` is
    None unless argparse raised SystemExit.
    """
    from skeleton.developer.cli import run_dev_cli

    out, err = io.StringIO(), io.StringIO()
    code: Optional[int] = None
    result: Any = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = run_dev_cli(list(argv))
        except SystemExit as exc:  # argparse errors / --help
            code = exc.code if isinstance(exc.code, int) else 1
    return result, out.getvalue(), err.getvalue(), code


def run_module(argv: List[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """Run ``python3 -m skeleton dev ...`` as a real subprocess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONHASHSEED", "0")
    return subprocess.run(
        [sys.executable, "-m", "skeleton", "dev", *argv],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def json_documents(text: str) -> List[Any]:
    """Decode every top-level JSON document in ``text`` (ignoring other lines)."""
    decoder = json.JSONDecoder()
    docs: List[Any] = []
    idx = 0
    n = len(text)
    while idx < n:
        ch = text[idx]
        if ch in "{[":
            try:
                obj, end = decoder.raw_decode(text, idx)
            except ValueError:
                idx += 1
                continue
            docs.append(obj)
            idx = end
        else:
            idx += 1
    return docs


def first_json(text: str) -> Any:
    docs = json_documents(text)
    if not docs:
        raise AssertionError(f"no JSON document in output: {text[:200]!r}")
    return docs[0]


GATE_KEYS = {"banner", "kind", "ok", "verdict"}
PASS_BANNER = "VERDICT: ALL GATES PASSED"
FAIL_PREFIX = "VERDICT: FAIL CLOSED"
