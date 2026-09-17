"""Named floats."""

from __future__ import annotations

from typing import Any


class FloatPackError(ValueError):
    pass


FLOAT = tuple(f"fl_{i:02d}" for i in range(12))


def work(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLOAT:
        raise FloatPackError(name)
    nxt = dict(node)
    nxt["float"] = name
    nxt["stored_prose"] = 0
    return nxt
