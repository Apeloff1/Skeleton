#!/usr/bin/env python3
"""Fail-closed GB-48 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.era.admit import admit  # noqa: E402


def main() -> int:
    ok = admit({"citation": "era_bind"})
    bad = admit({"citation": "has a sentence"})
    if ok["ok"] != 1 or bad["ok"] != 0 or bad["citation"] or "sentence" in json.dumps(bad):
        print("GB-48 FAIL", ok, bad)
        return 2
    print("GB-48 OK era admit token citation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
