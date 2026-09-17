"""Named endbands."""

from __future__ import annotations

from typing import Any


class EndbandPackError(ValueError):
    pass


END = tuple(f"eb_{i:02d}" for i in range(8))


def set_end(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in END:
        raise EndbandPackError(name)
    nxt = dict(state)
    nxt["endband"] = name
    nxt["stored_prose"] = 0
    return nxt
