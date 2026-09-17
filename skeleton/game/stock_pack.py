"""Named anchor stocks."""

from __future__ import annotations

from typing import Any


class StockPackError(ValueError):
    pass


STOCK = tuple(f"sk_{i:02d}" for i in range(8))


def set_stock(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STOCK:
        raise StockPackError(name)
    nxt = dict(state)
    nxt["stock"] = name
    nxt["stored_prose"] = 0
    return nxt
