"""Named furlongs."""

from __future__ import annotations

from typing import Any


class FurlongPackError(ValueError):
    pass


FURLONG = tuple(f"fl_{i:02d}" for i in range(8))


def measure(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in FURLONG:
        raise FurlongPackError(name)
    nxt = dict(state)
    nxt["furlong"] = name
    nxt["fur"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
