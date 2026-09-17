"""Named kilns."""

from __future__ import annotations

from typing import Any


class KilnPackError(ValueError):
    pass


KILN = tuple(f"kn_{i:02d}" for i in range(16))


def fire(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KILN:
        raise KilnPackError(name)
    nxt = dict(node)
    nxt["kiln"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 3)
    nxt["stored_prose"] = 0
    return nxt
