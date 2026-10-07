#!/usr/bin/env python3
"""Fail-closed GB-22 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.viscera.verify import run_all  # noqa: E402


def main() -> int:
    result = run_all()
    if result["ok"] != 1:
        print("GB-22 FAIL", result["failed"])
        return 2
    print("GB-22 OK specdec remat SNR no-torch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
