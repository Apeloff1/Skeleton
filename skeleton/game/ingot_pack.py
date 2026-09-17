"""Named ingots."""

from __future__ import annotations

from typing import Any


class IngotPackError(ValueError):
    pass


INGOT = tuple(f"ig_{i:02d}" for i in range(28))


def cast(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in INGOT:
        raise IngotPackError(name)
    nxt = dict(state)
    have = list(nxt.get("ingot") or [])
    have.append(name)
    nxt["ingot"] = have
    nxt["stored_prose"] = 0
    return nxt
