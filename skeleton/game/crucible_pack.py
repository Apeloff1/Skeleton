"""Named crucibles."""

from __future__ import annotations

from typing import Any


class CruciblePackError(ValueError):
    pass


CRUCIBLE = tuple(f"cr_{i:02d}" for i in range(20))


def fill(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CRUCIBLE:
        raise CruciblePackError(name)
    nxt = dict(node)
    nxt["crucible"] = name
    nxt["melt"] = 1
    nxt["stored_prose"] = 0
    return nxt
