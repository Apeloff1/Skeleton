"""Named stains. Pointer only."""

from __future__ import annotations

from typing import Any


class StainPackError(ValueError):
    pass


STAIN = tuple(f"st_{i:02d}" for i in range(28))


def set_stain(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAIN:
        raise StainPackError(name)
    nxt = dict(node)
    have = list(nxt.get("stain") or [])
    if name not in have:
        have.append(name)
    nxt["stain"] = have
    nxt["stored_prose"] = 0
    return nxt
