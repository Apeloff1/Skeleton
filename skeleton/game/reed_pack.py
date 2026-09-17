"""Named reeds."""

from __future__ import annotations

from typing import Any


class ReedPackError(ValueError):
    pass


REED = tuple(f"rd_{i:02d}" for i in range(12))


def beat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in REED:
        raise ReedPackError(name)
    nxt = dict(state)
    nxt["reed"] = name
    nxt["picks"] = int(nxt.get("picks", 0))
    nxt["stored_prose"] = 0
    return nxt
