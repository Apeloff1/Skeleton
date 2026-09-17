"""Named brood boxes."""

from __future__ import annotations

from typing import Any


class BroodPackError(ValueError):
    pass


BROOD = tuple(f"bd_{i:02d}" for i in range(8))


def set_brood(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BROOD:
        raise BroodPackError(name)
    nxt = dict(node)
    nxt["brood"] = name
    nxt["stored_prose"] = 0
    return nxt
