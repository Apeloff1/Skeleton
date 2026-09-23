#!/usr/bin/env python3
"""Fail-closed GB-40 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.genos import DNAHelix, Genos  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        card = Genos(DNAHelix(Path(td))).forge_emit("extraction")
        if card["n"] < 1 or card["stored_prose"] != 0:
            print("GB-40 FAIL", card)
            return 2
    print("GB-40 OK forge then genos n>=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
