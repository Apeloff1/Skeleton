#!/usr/bin/env python3
"""Fail-closed GB-46 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.cue import Cue  # noqa: E402
from skeleton.cue.law import AXES  # noqa: E402


def main() -> int:
    cue = Cue()
    card = {}
    for _ in range(5):
        card = cue.tick()
    bad = card["stored_prose"] != 0 or any(card["axis"][name] != 1 for name in AXES)
    leaked = cue.tick("keep this sentence out")
    blob = json.dumps(leaked)
    if bad or leaked["dropped"] != 1 or "sentence" in blob:
        print("GB-46 FAIL", card, leaked)
        return 2
    print("GB-46 OK five axes tokens only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
