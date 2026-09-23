#!/usr/bin/env python3
"""Fail-closed GB-52 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.place import place  # noqa: E402


def main() -> int:
    good = place(3, "card-a")
    bad = place(3, "keep this sentence out")
    blob = json.dumps(bad)
    if good["ok"] != 1 or bad["ok"] != 0 or bad["token"] or "sentence" in blob:
        print("GB-52 FAIL", good, bad)
        return 2
    print("GB-52 OK slot token no-sentence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
