"""Named millstones."""

from __future__ import annotations

from typing import Any


class MillstonePackError(ValueError):
    pass


STONE = tuple(f"ms_{i:02d}" for i in range(16))


def set_stone(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STONE:
        raise MillstonePackError(name)
    nxt = dict(node)
    nxt["stone"] = name
    nxt["stored_prose"] = 0
    return nxt
