"""Named indigo lots."""

from __future__ import annotations

from typing import Any


class IndigoPackError(ValueError):
    pass


INDIGO = tuple(f"in_{i:02d}" for i in range(12))


def dip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in INDIGO:
        raise IndigoPackError(name)
    nxt = dict(state)
    nxt["indigo"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
