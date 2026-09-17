"""Named indentures."""

from __future__ import annotations

from typing import Any


class IndenturePackError(ValueError):
    pass


IND = tuple(f"id_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in IND:
        raise IndenturePackError(name)
    nxt = dict(state)
    nxt["indenture"] = name
    nxt["cut"] = 1
    nxt["stored_prose"] = 0
    return nxt
