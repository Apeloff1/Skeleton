"""Named planchets."""

from __future__ import annotations

from typing import Any


class PlanchetPackError(ValueError):
    pass


PLAN = tuple(f"pl_{i:02d}" for i in range(16))


def blank(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PLAN:
        raise PlanchetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("planchet") or [])
    have.append(name)
    nxt["planchet"] = have
    nxt["stored_prose"] = 0
    return nxt
