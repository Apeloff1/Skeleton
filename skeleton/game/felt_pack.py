"""Named felts."""

from __future__ import annotations

from typing import Any


class FeltPackError(ValueError):
    pass


FELT = tuple(f"ft_{i:02d}" for i in range(12))


def press(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FELT:
        raise FeltPackError(name)
    nxt = dict(state)
    nxt["felt"] = name
    nxt["wet"] = max(0, int(nxt.get("wet", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
