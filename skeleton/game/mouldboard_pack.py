"""Named mouldboards."""

from __future__ import annotations

from typing import Any


class MouldboardPackError(ValueError):
    pass


BOARD = tuple(f"mb_{i:02d}" for i in range(8))


def set_board(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOARD:
        raise MouldboardPackError(name)
    nxt = dict(state)
    nxt["mouldboard"] = name
    nxt["turn"] = int(nxt.get("turn", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
