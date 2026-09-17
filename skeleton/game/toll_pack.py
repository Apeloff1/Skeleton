"""Named tolls. Spend scrap. No coin."""

from __future__ import annotations

from typing import Any


class TollPackError(ValueError):
    pass


TOLLS = tuple(f"tl_{i:02d}" for i in range(16))


def pay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TOLLS:
        raise TollPackError(name)
    nxt = dict(state)
    need = 1 + (TOLLS.index(name) % 3)
    if int(nxt.get("scrap", 0)) < need:
        raise TollPackError("scrap")
    nxt["scrap"] = int(nxt.get("scrap", 0)) - need
    nxt["toll"] = name
    nxt["stored_prose"] = 0
    return nxt
