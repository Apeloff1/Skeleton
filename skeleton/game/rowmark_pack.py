"""Named row marks."""

from __future__ import annotations

from typing import Any


class RowmarkPackError(ValueError):
    pass


MARK = tuple(f"rm_{i:02d}" for i in range(16))


def set_mark(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MARK:
        raise RowmarkPackError(name)
    nxt = dict(state)
    nxt["rowmark"] = name
    nxt["stored_prose"] = 0
    return nxt
