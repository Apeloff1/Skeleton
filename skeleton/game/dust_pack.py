"""Named dust layers."""

from __future__ import annotations

from typing import Any


class DustPackError(ValueError):
    pass


DUST = tuple(f"du_{i:02d}" for i in range(20))


def settle(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DUST:
        raise DustPackError(name)
    nxt = dict(node)
    nxt["dust"] = name
    nxt["los_pen"] = min(8, int(nxt.get("los_pen", 0)) + 1 + (DUST.index(name) % 2))
    nxt["stored_prose"] = 0
    return nxt
