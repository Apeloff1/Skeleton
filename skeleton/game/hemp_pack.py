"""Named hemp lots."""

from __future__ import annotations

from typing import Any


class HempPackError(ValueError):
    pass


HEMP = tuple(f"hm_{i:02d}" for i in range(16))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HEMP:
        raise HempPackError(name)
    nxt = dict(state)
    have = list(nxt.get("hemp") or [])
    have.append(name)
    nxt["hemp"] = have
    nxt["stored_prose"] = 0
    return nxt
