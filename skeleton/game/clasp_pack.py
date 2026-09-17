"""Named clasps."""

from __future__ import annotations

from typing import Any


class ClaspPackError(ValueError):
    pass


CLASP = tuple(f"cl_{i:02d}" for i in range(8))


def set_clasp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLASP:
        raise ClaspPackError(name)
    nxt = dict(state)
    nxt["clasp"] = name
    nxt["shut"] = 1
    nxt["stored_prose"] = 0
    return nxt
