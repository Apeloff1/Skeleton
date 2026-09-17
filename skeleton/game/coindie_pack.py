"""Named coin dies."""

from __future__ import annotations

from typing import Any


class CoindiePackError(ValueError):
    pass


DIE = tuple(f"cd_{i:02d}" for i in range(8))


def strike(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DIE:
        raise CoindiePackError(name)
    nxt = dict(state)
    nxt["coindie"] = name
    nxt["struck"] = int(nxt.get("struck", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
