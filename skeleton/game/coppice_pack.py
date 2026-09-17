"""Named coppice stools."""

from __future__ import annotations

from typing import Any


class CoppicePackError(ValueError):
    pass


COPPICE = tuple(f"cp_{i:02d}" for i in range(12))


def cut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COPPICE:
        raise CoppicePackError(name)
    nxt = dict(node)
    nxt["coppice"] = name
    nxt["growth"] = max(0, int(nxt.get("growth", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
