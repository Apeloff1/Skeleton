#!/usr/bin/env python3
"""Fail-closed GB-47 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.cue.fold import fold  # noqa: E402


def main() -> int:
    card = fold(["xarchive", "plan", "r1"])
    dropped = fold(["keep this sentence"])
    if card["id"] != "xarchive.plan.r1" or dropped["dropped"] != 1 or "sentence" in json.dumps(dropped):
        print("GB-47 FAIL", card, dropped)
        return 2
    print("GB-47 OK cue fold tokens only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
