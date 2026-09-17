"""Named galleys."""

from __future__ import annotations

from typing import Any


class GalleyPackError(ValueError):
    pass


GALLEY = tuple(f"gy_{i:02d}" for i in range(12))


def set_galley(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GALLEY:
        raise GalleyPackError(name)
    nxt = dict(state)
    nxt["galley"] = name
    nxt["stored_prose"] = 0
    return nxt
