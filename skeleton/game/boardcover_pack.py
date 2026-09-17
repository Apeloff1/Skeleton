"""Named cover boards."""

from __future__ import annotations

from typing import Any


class BoardcoverPackError(ValueError):
    pass


BOARD = tuple(f"bc_{i:02d}" for i in range(8))


def set_board(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOARD:
        raise BoardcoverPackError(name)
    nxt = dict(state)
    nxt["boardcover"] = name
    nxt["stored_prose"] = 0
    return nxt
