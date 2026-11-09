"""Lazy cue organ index. Does not import the 2560 modules."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).with_name("INDEX.csv")


def names() -> list[tuple[str, str, str]]:
    rows = []
    for line in INDEX.read_text(encoding="utf-8").splitlines()[1:]:
        cid, family, module = line.split(",")
        rows.append((cid, family, module))
    return rows
