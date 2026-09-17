"""Named dredges."""

from __future__ import annotations

from typing import Any


class DredgePackError(ValueError):
    pass


DREDGE = tuple(f"dg_{i:02d}" for i in range(8))


def tow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DREDGE:
        raise DredgePackError(name)
    nxt = dict(state)
    nxt["dredge"] = name
    nxt["haul"] = int(nxt.get("haul", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
