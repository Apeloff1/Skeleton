"""Named rail switches."""

from __future__ import annotations

from typing import Any


class SwitchPackError(ValueError):
    pass


SWITCH = tuple(f"sw_{i:02d}" for i in range(20))


def throw(node: dict[str, Any], name: str, left: int) -> dict[str, Any]:
    if name not in SWITCH:
        raise SwitchPackError(name)
    nxt = dict(node)
    nxt["switch"] = name
    nxt["left"] = int(bool(left))
    nxt["stored_prose"] = 0
    return nxt
