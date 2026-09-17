"""Named hearths."""

from __future__ import annotations

from typing import Any


class HearthPackError(ValueError):
    pass


HEARTH = tuple(f"ht_{i:02d}" for i in range(24))


def lite(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HEARTH:
        raise HearthPackError(name)
    nxt = dict(node)
    nxt["hearth"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
