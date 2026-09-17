"""Named deckles."""

from __future__ import annotations

from typing import Any


class DecklePackError(ValueError):
    pass


DECKLE = tuple(f"dk_{i:02d}" for i in range(12))


def set_deckle(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DECKLE:
        raise DecklePackError(name)
    nxt = dict(state)
    nxt["deckle"] = name
    nxt["stored_prose"] = 0
    return nxt
