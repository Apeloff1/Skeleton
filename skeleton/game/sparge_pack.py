"""Named sparges."""

from __future__ import annotations

from typing import Any


class SpargePackError(ValueError):
    pass


SPARGE = tuple(f"sg_{i:02d}" for i in range(8))


def rinse(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SPARGE:
        raise SpargePackError(name)
    nxt = dict(state)
    nxt["sparge"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
