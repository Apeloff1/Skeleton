"""Named tithes."""

from __future__ import annotations

from typing import Any


class TithePackError(ValueError):
    pass


TITHE = tuple(f"ti_{i:02d}" for i in range(12))


def levy(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in TITHE:
        raise TithePackError(name)
    nxt = dict(state)
    nxt["tithe"] = name
    nxt["tenth"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
