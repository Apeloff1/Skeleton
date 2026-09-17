"""Named anvils."""

from __future__ import annotations

from typing import Any


class AnvilPackError(ValueError):
    pass


ANVIL = tuple(f"av_{i:02d}" for i in range(12))


def set_anvil(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ANVIL:
        raise AnvilPackError(name)
    nxt = dict(node)
    nxt["anvil"] = name
    nxt["stored_prose"] = 0
    return nxt
