"""Named coin collars."""

from __future__ import annotations

from typing import Any


class CoincollarPackError(ValueError):
    pass


COLLAR = tuple(f"cc_{i:02d}" for i in range(8))


def set_collar(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COLLAR:
        raise CoincollarPackError(name)
    nxt = dict(state)
    nxt["coincollar"] = name
    nxt["stored_prose"] = 0
    return nxt
