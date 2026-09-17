"""Named foreshots."""

from __future__ import annotations

from typing import Any


class ForeshotPackError(ValueError):
    pass


FORE = tuple(f"fs_{i:02d}" for i in range(8))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FORE:
        raise ForeshotPackError(name)
    nxt = dict(state)
    nxt["foreshot"] = name
    nxt["cut"] = int(nxt.get("cut", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
