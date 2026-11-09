#!/usr/bin/env python3
"""Fail-closed GB-44 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.delta import delta  # noqa: E402


def main() -> int:
    moved = delta({"ticks": 0, "extract_count": 0, "warp_count": 0}, {"ticks": 20, "extract_count": 1, "warp_count": 1})
    same = {"ticks": 20, "extract_count": 1, "warp_count": 1}
    stamp = delta(same, dict(same))
    if moved["stamp"] != 0 or moved["rebuild"] != 0 or stamp["stamp"] != 1:
        print("GB-44 FAIL", moved, stamp)
        return 2
    print("GB-44 OK delta moves, identical cards do not rebuild")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
