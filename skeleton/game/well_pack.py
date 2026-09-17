"""Named wells."""

from __future__ import annotations

from typing import Any


class WellPackError(ValueError):
    pass


WELL = tuple(f"wl_{i:02d}" for i in range(16))


def draw(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WELL:
        raise WellPackError(name)
    nxt = dict(state)
    nxt["well"] = name
    nxt["water"] = int(nxt.get("water", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
