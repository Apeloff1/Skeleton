"""Named gnomons."""

from __future__ import annotations

from typing import Any


class GnomonPackError(ValueError):
    pass


GNOMON = tuple(f"gn_{i:02d}" for i in range(8))


def set_gnomon(node: dict[str, Any], name: str, h: int) -> dict[str, Any]:
    if name not in GNOMON:
        raise GnomonPackError(name)
    nxt = dict(node)
    nxt["gnomon"] = name
    nxt["h"] = max(1, int(h))
    nxt["stored_prose"] = 0
    return nxt
