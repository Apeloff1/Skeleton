#!/usr/bin/env python3
"""Fail-closed GB-53 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.stock import stock  # noqa: E402


def main() -> int:
    card = stock([
        {"slot": 0, "token": "card-a"},
        {"slot": 0, "token": "card-b"},
        {"slot": 1, "token": "keep this sentence out"},
    ])
    blob = json.dumps(card)
    if card["n"] != 1 or card["collision"] != 1 or card["dropped"] != 1 or "sentence" in blob:
        print("GB-53 FAIL", card)
        return 2
    print("GB-53 OK unique slots collision drop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
