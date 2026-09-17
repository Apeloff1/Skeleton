"""Named wick trims."""

from __future__ import annotations

from typing import Any


class WicktrimPackError(ValueError):
    pass


TRIM = tuple(f"wt_{i:02d}" for i in range(12))


def trim(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRIM:
        raise WicktrimPackError(name)
    nxt = dict(state)
    nxt["wicktrim"] = name
    nxt["light"] = min(16, int(nxt.get("light", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
