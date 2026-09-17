"""Named straps."""

from __future__ import annotations

from typing import Any


class StrapPackError(ValueError):
    pass


STRAP = tuple(f"sp_{i:02d}" for i in range(8))


def bind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STRAP:
        raise StrapPackError(name)
    nxt = dict(state)
    nxt["strap"] = name
    nxt["tight"] = 1
    nxt["stored_prose"] = 0
    return nxt
