"""Named pulp lots."""

from __future__ import annotations

from typing import Any


class PulpPackError(ValueError):
    pass


PULP = tuple(f"pu_{i:02d}" for i in range(12))


def beat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PULP:
        raise PulpPackError(name)
    nxt = dict(state)
    nxt["pulp"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
