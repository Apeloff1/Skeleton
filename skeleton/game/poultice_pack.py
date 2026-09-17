"""Named poultices."""

from __future__ import annotations

from typing import Any


class PoulticePackError(ValueError):
    pass


POULT = tuple(f"po_{i:02d}" for i in range(16))


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in POULT:
        raise PoulticePackError(name)
    nxt = dict(state)
    nxt["poultice"] = name
    nxt["hp"] = min(40, int(nxt.get("hp", 40)) + 2)
    nxt["stored_prose"] = 0
    return nxt
