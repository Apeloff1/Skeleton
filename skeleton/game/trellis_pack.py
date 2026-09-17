"""Named trellises."""

from __future__ import annotations

from typing import Any


class TrellisPackError(ValueError):
    pass


TRELLIS = tuple(f"tr_{i:02d}" for i in range(12))


def set_trellis(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRELLIS:
        raise TrellisPackError(name)
    nxt = dict(node)
    nxt["trellis"] = name
    nxt["stored_prose"] = 0
    return nxt
