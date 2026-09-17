"""Named hoppers."""

from __future__ import annotations

from typing import Any


class HopperPackError(ValueError):
    pass


HOPPER = tuple(f"hp_{i:02d}" for i in range(16))


def fill(node: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in HOPPER:
        raise HopperPackError(name)
    nxt = dict(node)
    nxt["hopper"] = name
    nxt["grain"] = int(nxt.get("grain", 0)) + int(n)
    nxt["stored_prose"] = 0
    return nxt
