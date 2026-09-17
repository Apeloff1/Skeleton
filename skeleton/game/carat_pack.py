"""Named carat grades."""

from __future__ import annotations

from typing import Any


class CaratPackError(ValueError):
    pass


CARAT = tuple(f"ct_{i:02d}" for i in range(12))


def set_carat(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in CARAT:
        raise CaratPackError(name)
    nxt = dict(state)
    nxt["carat"] = name
    nxt["kt"] = max(1, min(24, int(n)))
    nxt["stored_prose"] = 0
    return nxt
