"""Named silt beds."""

from __future__ import annotations

from typing import Any


class SiltPackError(ValueError):
    pass


SILT = tuple(f"si_{i:02d}" for i in range(20))


def settle(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SILT:
        raise SiltPackError(name)
    nxt = dict(node)
    nxt["silt"] = name
    nxt["slow"] = int(nxt.get("slow", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
