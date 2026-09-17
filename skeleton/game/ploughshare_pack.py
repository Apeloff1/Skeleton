"""Named ploughshares."""

from __future__ import annotations

from typing import Any


class PloughsharePackError(ValueError):
    pass


SHARE = tuple(f"ps_{i:02d}" for i in range(8))


def set_share(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHARE:
        raise PloughsharePackError(name)
    nxt = dict(state)
    nxt["ploughshare"] = name
    nxt["stored_prose"] = 0
    return nxt
