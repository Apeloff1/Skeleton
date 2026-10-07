#!/usr/bin/env python3
"""Fail-closed GB-55 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.decode import decode  # noqa: E402


def main() -> int:
    opened = decode("r2")
    blocked = decode("r3halt", 0)
    leaked = decode("keep this sentence out", 1)
    blob = json.dumps(leaked)
    if opened["ok"] != 1 or opened["r"] != 2 or blocked["ok"] != 0 or leaked["ok"] != 0 or "sentence" in blob:
        print("GB-55 FAIL", opened, blocked, leaked)
        return 2
    print("GB-55 OK r2 pass r3halt needs halt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
