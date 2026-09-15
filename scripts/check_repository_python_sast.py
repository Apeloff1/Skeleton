"""Extend the canonical Python SAST gate beyond ``backend/``.

The high-confidence scanner lives in ``backend/scripts/check_sast_security.py``.
Historically its Python file enumeration covered only ``backend/`` which left the
production ``skeleton/`` package and top-level repository tooling outside that
security boundary.  Reuse the same violation engine here so the policy remains
single-sourced while coverage spans the rest of the Python runtime/tooling
surface.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys
from collections.abc import Callable, Iterable
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_SCANNER = REPO_ROOT / "backend" / "scripts" / "check_sast_security.py"
SCAN_ROOTS = (
    REPO_ROOT / "skeleton",
    REPO_ROOT / "scripts",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    "coverage",
}


def python_files() -> Iterable[Path]:
    """Yield repository Python files not already covered by the backend gate."""
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            yield path


def _load_violation_engine() -> Callable[[Path], list[str]]:
    if not BASE_SCANNER.is_file():
        raise RuntimeError(f"canonical SAST scanner missing: {BASE_SCANNER}")
    namespace: dict[str, Any] = runpy.run_path(str(BASE_SCANNER))
    engine = namespace.get("violations")
    if not callable(engine):
        raise RuntimeError("canonical SAST scanner does not expose violations(path)")
    return engine


def main() -> int:
    try:
        violations = _load_violation_engine()
    except Exception as exc:
        print(f"Repository Python SAST bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    count = 0
    for path in python_files():
        count += 1
        findings.extend(violations(path))

    if findings:
        print("High-confidence repository Python SAST violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(f"Repository Python SAST gate passed ({count} core/tooling Python files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
