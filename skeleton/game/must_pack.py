"""Named must lots."""

from __future__ import annotations

from typing import Any


class MustPackError(ValueError):
    pass


MUST = tuple(f"mu_{i:02d}" for i in range(12))


def press(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MUST:
        raise MustPackError(name)
    nxt = dict(state)
    nxt["must"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
