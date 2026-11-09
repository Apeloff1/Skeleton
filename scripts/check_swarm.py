#!/usr/bin/env python3
"""Fail-closed GB-29 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.swarm import handoff  # noqa: E402


def main() -> int:
    card = handoff("a1", "a2", "cut")
    if card.get("state") != "accept":
        print("GB-29 FAIL", card)
        return 2
    print("GB-29 OK handoff n-cap=8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
