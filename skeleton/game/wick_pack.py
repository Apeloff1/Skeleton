"""Named wicks."""

from __future__ import annotations

from typing import Any


class WickPackError(ValueError):
    pass


WICK = tuple(f"wk_{i:02d}" for i in range(16))


def set_wick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WICK:
        raise WickPackError(name)
    nxt = dict(state)
    have = list(nxt.get("wick") or [])
    have.append(name)
    nxt["wick"] = have
    nxt["stored_prose"] = 0
    return nxt
