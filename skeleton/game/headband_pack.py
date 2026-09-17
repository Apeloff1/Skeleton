"""Named headbands."""

from __future__ import annotations

from typing import Any


class HeadbandPackError(ValueError):
    pass


HEAD = tuple(f"hb_{i:02d}" for i in range(8))


def set_head(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HEAD:
        raise HeadbandPackError(name)
    nxt = dict(state)
    nxt["headband"] = name
    nxt["stored_prose"] = 0
    return nxt
