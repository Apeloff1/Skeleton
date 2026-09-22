#!/usr/bin/env python3
"""Fail-closed GB-42 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.parse import split  # noqa: E402


def main() -> int:
    card = split("see https://arxiv.org/abs/x and github.com/Apeloff1/Skeleton")
    if card["n"] != 2 or card["stored_prose"] != 0:
        print("GB-42 FAIL", card)
        return 2
    print("GB-42 OK n=2 stored_prose=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
