#!/usr/bin/env python3
"""Fail-closed GB-27 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.persist.verify import run_all  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_all(tmp)
    if result["ok"] != 1:
        print("GB-27 FAIL", result["failed"])
        return 2
    print("GB-27 OK local-gate disk-gate one-core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
