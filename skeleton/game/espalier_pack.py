"""Named espaliers."""

from __future__ import annotations

from typing import Any


class EspalierPackError(ValueError):
    pass


ESP = tuple(f"es_{i:02d}" for i in range(8))


def train(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ESP:
        raise EspalierPackError(name)
    nxt = dict(node)
    nxt["espalier"] = name
    nxt["stored_prose"] = 0
    return nxt
