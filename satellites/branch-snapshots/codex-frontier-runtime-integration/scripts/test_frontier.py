#!/usr/bin/env python3
"""Run every promoted frontier contract and application integration test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    "skeleton/testing/test_frontier_*.py",
    "tests/test_frontier_*.py",
    "tests/test_gameforge_*.py",
    "tests/test_admission_contract.py",
    "tests/test_recovery_contract.py",
    "tests/test_kernel_event_pipeline_contract.py",
)


def main() -> int:
    paths = set()
    for pattern in PATTERNS:
        matches = list(ROOT.glob(pattern))
        if not matches:
            raise RuntimeError(f"required test group is missing: {pattern}")
        paths.update(str(path.relative_to(ROOT)) for path in matches)
    return subprocess.call([sys.executable, "-m", "pytest", "-q", *sorted(paths), *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
