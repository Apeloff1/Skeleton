"""Named buttermilk lots."""

from __future__ import annotations

from typing import Any


class ButtermilkPackError(ValueError):
    pass


MILK = tuple(f"bm_{i:02d}" for i in range(12))


def drain(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MILK:
        raise ButtermilkPackError(name)
    nxt = dict(state)
    nxt["buttermilk"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
