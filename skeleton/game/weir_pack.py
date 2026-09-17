"""Named weirs."""

from __future__ import annotations

from typing import Any


class WeirPackError(ValueError):
    pass


WEIR = tuple(f"wr_{i:02d}" for i in range(8))


def set_weir(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WEIR:
        raise WeirPackError(name)
    nxt = dict(node)
    nxt["weir"] = name
    nxt["stored_prose"] = 0
    return nxt
