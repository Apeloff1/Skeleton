"""Named knots."""

from __future__ import annotations

from typing import Any


class KnotPackError(ValueError):
    pass


KNOT = tuple(f"kn_{i:02d}" for i in range(20))


def tie(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KNOT:
        raise KnotPackError(name)
    nxt = dict(state)
    have = list(nxt.get("knot") or [])
    if name not in have:
        have.append(name)
    nxt["knot"] = have
    nxt["stored_prose"] = 0
    return nxt
