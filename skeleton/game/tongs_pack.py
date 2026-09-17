"""Named tongs."""

from __future__ import annotations

from typing import Any


class TongsPackError(ValueError):
    pass


TONGS = tuple(f"tg_{i:02d}" for i in range(8))


def grip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TONGS:
        raise TongsPackError(name)
    nxt = dict(state)
    nxt["tongs"] = name
    nxt["take"] = int(nxt.get("take", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
