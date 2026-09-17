"""Named bungs."""

from __future__ import annotations

from typing import Any


class BungPackError(ValueError):
    pass


BUNG = tuple(f"bg_{i:02d}" for i in range(16))


def set_bung(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BUNG:
        raise BungPackError(name)
    nxt = dict(state)
    nxt["bung"] = name
    nxt["sealed"] = 1
    nxt["stored_prose"] = 0
    return nxt
