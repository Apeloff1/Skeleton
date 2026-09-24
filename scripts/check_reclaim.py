#!/usr/bin/env python3
"""Fail-closed GB-56 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.reclaim import reclaim  # noqa: E402


def main() -> int:
    good = reclaim([0, 2], [2])
    bad = reclaim([0], ["keep this sentence out"])
    blob = json.dumps(bad)
    if good["ok"] != 1 or good["slots"] != [2] or good["remain"] != [0]:
        print("GB-56 FAIL", good, bad)
        return 2
    if bad["ok"] != 0 or bad["slots"] or "sentence" in blob:
        print("GB-56 FAIL", good, bad)
        return 2
    print("GB-56 OK free held no-sentence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
