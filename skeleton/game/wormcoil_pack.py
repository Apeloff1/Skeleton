"""Named worm coils."""

from __future__ import annotations

from typing import Any


class WormcoilPackError(ValueError):
    pass


WORM = tuple(f"wc_{i:02d}" for i in range(8))


def set_worm(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WORM:
        raise WormcoilPackError(name)
    nxt = dict(state)
    nxt["wormcoil"] = name
    nxt["cool"] = int(nxt.get("cool", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
