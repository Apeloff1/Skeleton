"""Named molds."""

from __future__ import annotations

from typing import Any


class MoldPackError(ValueError):
    pass


MOLD = tuple(f"md_{i:02d}" for i in range(20))


def pour(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MOLD:
        raise MoldPackError(name)
    nxt = dict(state)
    nxt["mold"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
