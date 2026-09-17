"""Named presses."""

from __future__ import annotations

from typing import Any


class PressPackError(ValueError):
    pass


PRESS = tuple(f"ps_{i:02d}" for i in range(12))


def squeeze(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PRESS:
        raise PressPackError(name)
    nxt = dict(state)
    nxt["press"] = name
    nxt["must"] = int(nxt.get("must", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
