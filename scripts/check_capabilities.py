#!/usr/bin/env python3
"""Fail-closed GB-36 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.frontier.capabilities import collect, capabilities  # noqa: E402


def main() -> int:
    cards = collect()
    cap = capabilities()
    if cap.get("packet") != "GB-36":
        print("GB-36 FAIL packet")
        return 2
    print("GB-36 OK n=%d empty_ok=1" % len(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
