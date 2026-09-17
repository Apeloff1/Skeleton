"""Named lye lots."""

from __future__ import annotations

from typing import Any


class LyePackError(ValueError):
    pass


LYE = tuple(f"ly_{i:02d}" for i in range(12))


def leach(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LYE:
        raise LyePackError(name)
    nxt = dict(state)
    nxt["lye"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
