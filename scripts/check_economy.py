#!/usr/bin/env python3
"""Fail-closed GB-45 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.economy import Harbor  # noqa: E402


def main() -> int:
    h = Harbor({"house": 0.4, "lineage": 0.6})
    h.put("card-a")
    h.undo()
    if not h.balanced() or h.bag or h.card()["coin"] != 0:
        print("GB-45 FAIL", h.card())
        return 2
    print("GB-45 OK sum=1 reversible no-coin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
