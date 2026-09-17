"""Named tides."""

from __future__ import annotations

from typing import Any


class TidePackError(ValueError):
    pass


TIDE = tuple(f"td_{i:02d}" for i in range(16))


def rise(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TIDE:
        raise TidePackError(name)
    nxt = dict(node)
    nxt["tide"] = name
    nxt["level"] = TIDE.index(name) % 8
    nxt["stored_prose"] = 0
    return nxt
