"""Named cantles."""

from __future__ import annotations

from typing import Any


class CantlePackError(ValueError):
    pass


CANTLE = tuple(f"ct_{i:02d}" for i in range(8))


def set_cantle(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CANTLE:
        raise CantlePackError(name)
    nxt = dict(state)
    nxt["cantle"] = name
    nxt["stored_prose"] = 0
    return nxt
