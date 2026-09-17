"""Named fines. Scrap only. No coin."""

from __future__ import annotations

from typing import Any


class FinePackError(ValueError):
    pass


FINE = tuple(f"fn_{i:02d}" for i in range(16))


def levy(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FINE:
        raise FinePackError(name)
    nxt = dict(state)
    need = 1 + (FINE.index(name) % 3)
    if int(nxt.get("scrap", 0)) < need:
        raise FinePackError("scrap")
    nxt["scrap"] = int(nxt.get("scrap", 0)) - need
    nxt["fine"] = name
    nxt["stored_prose"] = 0
    return nxt
