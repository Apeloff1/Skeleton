"""Named mortars."""

from __future__ import annotations

from typing import Any


class MortarPackError(ValueError):
    pass


MORTAR = tuple(f"mt_{i:02d}" for i in range(16))


def mix(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MORTAR:
        raise MortarPackError(name)
    nxt = dict(state)
    have = list(nxt.get("mortar") or [])
    have.append(name)
    nxt["mortar"] = have
    nxt["stored_prose"] = 0
    return nxt
