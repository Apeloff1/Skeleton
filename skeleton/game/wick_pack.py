"""Named wicks."""

from __future__ import annotations

from typing import Any


class WickPackError(ValueError):
    pass


WICK = tuple(f"wk_{i:02d}" for i in range(16))


def light(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WICK:
        raise WickPackError(name)
    nxt = dict(state)
    nxt["wick"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
