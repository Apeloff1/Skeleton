"""Named clinker heaps."""

from __future__ import annotations

from typing import Any


class ClinkerPackError(ValueError):
    pass


CLINK = tuple(f"ck_{i:02d}" for i in range(16))


def heap(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLINK:
        raise ClinkerPackError(name)
    nxt = dict(node)
    nxt["clinker"] = int(nxt.get("clinker", 0)) + 1 + (CLINK.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
