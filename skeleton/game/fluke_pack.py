"""Named flukes."""

from __future__ import annotations

from typing import Any


class FlukePackError(ValueError):
    pass


FLUKE = tuple(f"fk_{i:02d}" for i in range(12))


def set_fluke(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLUKE:
        raise FlukePackError(name)
    nxt = dict(state)
    nxt["fluke"] = name
    nxt["hold"] = int(nxt.get("hold", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
