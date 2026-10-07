#!/usr/bin/env python3
"""Fail-closed GB-50 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.check import check  # noqa: E402


def main() -> int:
    moved = check({"stamp": 0, "rebuild": 0})
    stamp = check({"stamp": 1, "rebuild": 0, "note": "keep this sentence out"})
    blob = json.dumps(stamp)
    if moved["ok"] != 1 or stamp["ok"] != 0 or "sentence" in blob:
        print("GB-50 FAIL", moved, stamp)
        return 2
    print("GB-50 OK move passes stamp fails")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
