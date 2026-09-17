"""Named pastes."""

from __future__ import annotations

from typing import Any


class PastePackError(ValueError):
    pass


PASTE = tuple(f"ps_{i:02d}" for i in range(8))


def glue(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PASTE:
        raise PastePackError(name)
    nxt = dict(state)
    nxt["paste"] = name
    nxt["stuck"] = 1
    nxt["stored_prose"] = 0
    return nxt
