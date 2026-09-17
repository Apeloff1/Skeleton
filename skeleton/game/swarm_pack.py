"""Named swarms."""

from __future__ import annotations

from typing import Any


class SwarmPackError(ValueError):
    pass


SWARM = tuple(f"sw_{i:02d}" for i in range(12))


def lift(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SWARM:
        raise SwarmPackError(name)
    nxt = dict(node)
    nxt["swarm"] = name
    nxt["alert"] = int(nxt.get("alert", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
