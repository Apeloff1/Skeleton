"""Named cheeses."""

from __future__ import annotations

from typing import Any


class CheesePackError(ValueError):
    pass


CHEESE = tuple(f"ch_{i:02d}" for i in range(16))


def age(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHEESE:
        raise CheesePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cheese") or [])
    have.append(name)
    nxt["cheese"] = have
    nxt["stored_prose"] = 0
    return nxt
