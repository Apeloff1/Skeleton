"""Named hop lots."""

from __future__ import annotations

from typing import Any


class HopsPackError(ValueError):
    pass


HOPS = tuple(f"hp_{i:02d}" for i in range(12))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HOPS:
        raise HopsPackError(name)
    nxt = dict(state)
    have = list(nxt.get("hops") or [])
    have.append(name)
    nxt["hops"] = have
    nxt["stored_prose"] = 0
    return nxt
