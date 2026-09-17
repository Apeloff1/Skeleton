"""Named rootstocks."""

from __future__ import annotations

from typing import Any


class RootstockPackError(ValueError):
    pass


ROOT = tuple(f"rs_{i:02d}" for i in range(12))


def set_root(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROOT:
        raise RootstockPackError(name)
    nxt = dict(state)
    nxt["rootstock"] = name
    nxt["stored_prose"] = 0
    return nxt
