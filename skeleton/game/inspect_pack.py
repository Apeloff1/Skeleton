"""Named inspections."""

from __future__ import annotations

from typing import Any


class InspectPackError(ValueError):
    pass


INSP = tuple(f"in_{i:02d}" for i in range(20))


def run(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in INSP:
        raise InspectPackError(name)
    nxt = dict(state)
    nxt["inspect"] = name
    nxt["alert"] = int(nxt.get("alert", 0)) + (INSP.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
