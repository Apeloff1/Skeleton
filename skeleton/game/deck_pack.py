"""Named decks."""

from __future__ import annotations

from typing import Any


class DeckPackError(ValueError):
    pass


DECK = tuple(f"dk_{i:02d}" for i in range(16))


def lay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DECK:
        raise DeckPackError(name)
    nxt = dict(node)
    nxt["deck"] = name
    nxt["stored_prose"] = 0
    return nxt
