"""Named prunes."""

from __future__ import annotations

from typing import Any


class PrunePackError(ValueError):
    pass


PRUNE = tuple(f"pn_{i:02d}" for i in range(16))


def cut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PRUNE:
        raise PrunePackError(name)
    nxt = dict(node)
    nxt["prune"] = name
    nxt["growth"] = max(0, int(nxt.get("growth", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
