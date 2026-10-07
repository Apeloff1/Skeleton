#!/usr/bin/env python3
"""Fail-closed GB-41 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn import TurnEngine  # noqa: E402


def main() -> int:
    card = TurnEngine().run(20)
    if card["extract_count"] != card["warp_count"] or card["ticks"] != 20:
        print("GB-41 FAIL", card)
        return 2
    print("GB-41 OK 20-tick extract==warp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
