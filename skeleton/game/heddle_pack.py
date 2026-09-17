"""Named heddles."""

from __future__ import annotations

from typing import Any


class HeddlePackError(ValueError):
    pass


HEDDLE = tuple(f"hd_{i:02d}" for i in range(16))


def lift(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HEDDLE:
        raise HeddlePackError(name)
    nxt = dict(node)
    nxt["heddle"] = name
    nxt["shed"] = 1
    nxt["stored_prose"] = 0
    return nxt
