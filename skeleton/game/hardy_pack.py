"""Named hardies."""

from __future__ import annotations

from typing import Any


class HardyPackError(ValueError):
    pass


HARDY = tuple(f"hy_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HARDY:
        raise HardyPackError(name)
    nxt = dict(state)
    nxt["hardy"] = name
    nxt["scrap"] = int(nxt.get("scrap", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
