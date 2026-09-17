"""Named warps."""

from __future__ import annotations

from typing import Any


class WarpPackError(ValueError):
    pass


WARP = tuple(f"wp_{i:02d}" for i in range(16))


def beam(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WARP:
        raise WarpPackError(name)
    nxt = dict(state)
    nxt["warp"] = name
    nxt["stored_prose"] = 0
    return nxt
