#!/usr/bin/env python3
"""Fail-closed GB-49 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.genos.pair import admit_pair  # noqa: E402


def main() -> int:
    ok = admit_pair("forge", "extraction")
    bad = admit_pair("has a sentence", "extraction")
    if ok["ok"] != 1 or bad["n"] != 0 or "sentence" in json.dumps(bad):
        print("GB-49 FAIL", ok, bad)
        return 2
    print("GB-49 OK genos pair tokens only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
