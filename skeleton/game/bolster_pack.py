"""Named bolsters."""

from __future__ import annotations

from typing import Any


class BolsterPackError(ValueError):
    pass


BOLSTER = tuple(f"bo_{i:02d}" for i in range(8))


def set_bolster(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOLSTER:
        raise BolsterPackError(name)
    nxt = dict(state)
    nxt["bolster"] = name
    nxt["stored_prose"] = 0
    return nxt
