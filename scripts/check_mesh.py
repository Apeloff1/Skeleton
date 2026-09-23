#!/usr/bin/env python3
"""Fail-closed GB-43 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.parse.mesh import scan  # noqa: E402


def main() -> int:
    clean = scan({"tokens": ["why", "how"]})
    dirty = scan({"note": "see the long sentence"})
    blob = json.dumps(dirty)
    if clean["hits"] != 0 or dirty["doctor"] != 1 or "sentence" in blob:
        print("GB-43 FAIL", clean, dirty)
        return 2
    print("GB-43 OK mesh counts sentences and does not keep them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
