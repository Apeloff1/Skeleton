"""Named valleys."""

from __future__ import annotations

from typing import Any


class ValleyPackError(ValueError):
    pass


VALLEY = tuple(f"vl_{i:02d}" for i in range(12))


def set_valley(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VALLEY:
        raise ValleyPackError(name)
    nxt = dict(node)
    nxt["valley"] = name
    nxt["stored_prose"] = 0
    return nxt
