"""Named brine lots."""

from __future__ import annotations

from typing import Any


class BrinePackError(ValueError):
    pass


BRINE = tuple(f"br_{i:02d}" for i in range(16))


def fill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BRINE:
        raise BrinePackError(name)
    nxt = dict(state)
    nxt["brine"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
