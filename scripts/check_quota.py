#!/usr/bin/env python3
"""Fail-closed GB-51 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.economy.quota import CAP, admit  # noqa: E402


def main() -> int:
    card = admit(["card-a"] * (CAP + 1) + ["keep this sentence out"])
    blob = json.dumps(card)
    if card["n"] != CAP or card["dropped"] < 2 or card["coin"] != 0 or "sentence" in blob:
        print("GB-51 FAIL", card)
        return 2
    print("GB-51 OK cap=8 no-coin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
