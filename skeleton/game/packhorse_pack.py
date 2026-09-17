"""Named packhorses."""

from __future__ import annotations

from typing import Any


class PackhorsePackError(ValueError):
    pass


PACK = tuple(f"ph_{i:02d}" for i in range(8))


def load(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in PACK:
        raise PackhorsePackError(name)
    nxt = dict(state)
    nxt["packhorse"] = name
    nxt["load"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
