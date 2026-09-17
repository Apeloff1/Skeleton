"""Named braces."""

from __future__ import annotations

from typing import Any


class BracePackError(ValueError):
    pass


BRACE = tuple(f"br_{i:02d}" for i in range(24))


def set_brace(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BRACE:
        raise BracePackError(name)
    nxt = dict(node)
    nxt["brace"] = name
    nxt["stress"] = max(0, int(nxt.get("stress", 0)) - 2)
    nxt["stored_prose"] = 0
    return nxt
