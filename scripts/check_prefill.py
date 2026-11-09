#!/usr/bin/env python3
"""Fail-closed GB-54 gate. Exit 2 on miss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.turn.prefill import prefill  # noqa: E402


def main() -> int:
    good = prefill([1], "pad")
    bad = prefill([1], "keep this sentence out")
    blob = json.dumps(bad)
    if good["ok"] != 1 or good["n"] != 7 or bad["ok"] != 0 or bad["slots"] or "sentence" in blob:
        print("GB-54 FAIL", good, bad)
        return 2
    print("GB-54 OK empty slots no-sentence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
