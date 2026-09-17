"""Named cart axles."""

from __future__ import annotations

from typing import Any


class CartaxlePackError(ValueError):
    pass


AXLE = tuple(f"ax_{i:02d}" for i in range(8))


def set_axle(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in AXLE:
        raise CartaxlePackError(name)
    nxt = dict(state)
    nxt["cartaxle"] = name
    nxt["stored_prose"] = 0
    return nxt
