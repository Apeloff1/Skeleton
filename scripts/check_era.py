#!/usr/bin/env python3
"""Fail-closed GB-39 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.era import forge  # noqa: E402


def main() -> int:
    card = forge("extraction")
    if card["reference"] != "era_bind" or card["stored_prose"] != 0:
        print("GB-39 FAIL", card)
        return 2
    print("GB-39 OK forge citation stored_prose=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
