#!/usr/bin/env python3
"""Fail-closed GB-57 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.walk import walk  # noqa: E402


def main() -> int:
    good = walk(["admit", "quota"])
    skip = walk(["quota"])
    leaked = walk(["keep this sentence out"])
    blob = json.dumps(leaked)
    if good["ok"] != 1 or good["n"] != 2 or skip["ok"] != 0 or leaked["ok"] != 0 or "sentence" in blob:
        print("GB-57 FAIL", good, skip, leaked)
        return 2
    print("GB-57 OK order no-sentence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
