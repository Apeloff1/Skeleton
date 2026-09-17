"""Named embers."""

from __future__ import annotations

from typing import Any


class EmberPackError(ValueError):
    pass


EMBER = tuple(f"em_{i:02d}" for i in range(24))


def drop(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in EMBER:
        raise EmberPackError(name)
    nxt = dict(node)
    nxt["ember"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1 + (EMBER.index(name) % 3))
    nxt["stored_prose"] = 0
    return nxt
