"""Named inquisitions."""

from __future__ import annotations

from typing import Any


class InquisitionPackError(ValueError):
    pass


INQ = tuple(f"iq_{i:02d}" for i in range(12))


def hold(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in INQ:
        raise InquisitionPackError(name)
    nxt = dict(state)
    nxt["inquisition"] = name
    nxt["held"] = 1
    nxt["stored_prose"] = 0
    return nxt
