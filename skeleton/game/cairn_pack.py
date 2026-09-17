"""Named cairns."""

from __future__ import annotations

from typing import Any


class CairnPackError(ValueError):
    pass


CAIRN = tuple(f"cn_{i:02d}" for i in range(12))


def set_cairn(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CAIRN:
        raise CairnPackError(name)
    nxt = dict(node)
    nxt["cairn"] = name
    nxt["stored_prose"] = 0
    return nxt
