"""Named sprues."""

from __future__ import annotations

from typing import Any


class SpruePackError(ValueError):
    pass


SPRUE = tuple(f"sp_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SPRUE:
        raise SpruePackError(name)
    nxt = dict(state)
    nxt["sprue"] = name
    nxt["scrap"] = int(nxt.get("scrap", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
