"""Named ridges."""

from __future__ import annotations

from typing import Any


class RidgePackError(ValueError):
    pass


RIDGE = tuple(f"rg_{i:02d}" for i in range(12))


def cap(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RIDGE:
        raise RidgePackError(name)
    nxt = dict(node)
    nxt["ridge"] = name
    nxt["stored_prose"] = 0
    return nxt
