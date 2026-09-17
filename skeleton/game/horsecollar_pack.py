"""Named horse collars."""

from __future__ import annotations

from typing import Any


class HorsecollarPackError(ValueError):
    pass


COLLAR = tuple(f"hc_{i:02d}" for i in range(8))


def set_collar(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COLLAR:
        raise HorsecollarPackError(name)
    nxt = dict(state)
    nxt["horsecollar"] = name
    nxt["stored_prose"] = 0
    return nxt
