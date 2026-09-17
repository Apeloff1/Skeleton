"""Named tongs."""

from __future__ import annotations

from typing import Any


class TongsPackError(ValueError):
    pass


TONGS = tuple(f"tg_{i:02d}" for i in range(20))


def grip(state: dict[str, Any], name: str, item: str) -> dict[str, Any]:
    if name not in TONGS:
        raise TongsPackError(name)
    nxt = dict(state)
    nxt["tongs"] = name
    nxt["held"] = item
    nxt["stored_prose"] = 0
    return nxt
