"""Named whey lots."""

from __future__ import annotations

from typing import Any


class WheyPackError(ValueError):
    pass


WHEY = tuple(f"wy_{i:02d}" for i in range(12))


def drain(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WHEY:
        raise WheyPackError(name)
    nxt = dict(state)
    nxt["whey"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
