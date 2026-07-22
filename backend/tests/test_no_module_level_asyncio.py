"""
tests/test_no_module_level_asyncio.py

★ K8s deployment regression guard.

Background: In Feb 2026 a production crash loop was traced to module-level
``asyncio.Lock()`` (also Event / Semaphore / Queue / Condition) instances.
Uvicorn creates the event loop AFTER module import, so any primitive bound at
import time ends up tied to a dead loop and crashes with::

    TypeError: 'NoneType' object does not support the asynchronous context
    manager protocol

The fix is to use a lazy getter:

    _lock: asyncio.Lock | None = None
    def _get_lock() -> asyncio.Lock:
        global _lock
        if _lock is None:
            _lock = asyncio.Lock()
        return _lock

This test scans every .py file under /app/backend and FAILS if it finds a
module-level instantiation. Type annotations like
``_lock: asyncio.Lock | None = None`` are allowed (no parens after Lock).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

#  Look for an unindented (=module-level) assignment whose RHS contains an
#  asyncio primitive WITH a call: ``asyncio.Lock(`` / ``asyncio.Event(``.
#  The `\(` is the critical anchor — `_lock: asyncio.Lock | None = None` is OK.
FORBIDDEN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*asyncio\.(Lock|Event|Semaphore|Queue|Condition)\s*\(",
    re.MULTILINE,
)

#  Files we skip — third-party, caches, tests themselves.
EXCLUDE = {".pytest_cache", ".ruff_cache", "__pycache__", ".venv", "venv", "tests"}


def _backend_py_files():
    for p in BACKEND.rglob("*.py"):
        if any(part in EXCLUDE for part in p.parts):
            continue
        yield p


def test_no_module_level_asyncio_primitives():
    violations: list[tuple[Path, int, str]] = []
    for py in _backend_py_files():
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in FORBIDDEN.finditer(text):
            #  Report 1-indexed line number for grep-ability.
            line_no = text.count("\n", 0, m.start()) + 1
            snippet = text[m.start(): m.start() + 80].splitlines()[0]
            violations.append((py.relative_to(BACKEND), line_no, snippet))

    if violations:
        report = "\n".join(
            f"  {p}:{ln}  {snippet}" for p, ln, snippet in violations
        )
        pytest.fail(
            "Module-level asyncio primitives detected — these will crash "
            "in Kubernetes with 'NoneType does not support asynchronous "
            "context manager protocol'. Replace with a lazy _get_lock() "
            "function:\n" + report
        )


if __name__ == "__main__":  # quick smoke-run from CLI
    test_no_module_level_asyncio_primitives()
    print("OK — no module-level asyncio primitives found.")
