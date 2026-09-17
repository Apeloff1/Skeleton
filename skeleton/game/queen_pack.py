"""Named queens."""

from __future__ import annotations

from typing import Any


class QueenPackError(ValueError):
    pass


QUEEN = tuple(f"qn_{i:02d}" for i in range(12))


def set_queen(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in QUEEN:
        raise QueenPackError(name)
    nxt = dict(node)
    nxt["queen"] = name
    nxt["stored_prose"] = 0
    return nxt
