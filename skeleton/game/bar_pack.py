"""Named bars."""

from __future__ import annotations

from typing import Any


class BarPackError(ValueError):
    pass


BAR = tuple(f"br_{i:02d}" for i in range(8))


def set_bar(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BAR:
        raise BarPackError(name)
    nxt = dict(node)
    nxt["bar"] = name
    nxt["stored_prose"] = 0
    return nxt
