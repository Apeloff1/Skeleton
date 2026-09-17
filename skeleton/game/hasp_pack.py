"""Named hasps."""

from __future__ import annotations

from typing import Any


class HaspPackError(ValueError):
    pass


HASP = tuple(f"hp_{i:02d}" for i in range(8))


def set_hasp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HASP:
        raise HaspPackError(name)
    nxt = dict(state)
    nxt["hasp"] = name
    nxt["shut"] = 1
    nxt["stored_prose"] = 0
    return nxt
