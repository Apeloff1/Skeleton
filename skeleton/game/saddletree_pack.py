"""Named saddle trees."""

from __future__ import annotations

from typing import Any


class SaddletreePackError(ValueError):
    pass


TREE = tuple(f"st_{i:02d}" for i in range(8))


def set_tree(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TREE:
        raise SaddletreePackError(name)
    nxt = dict(state)
    nxt["saddletree"] = name
    nxt["stored_prose"] = 0
    return nxt
