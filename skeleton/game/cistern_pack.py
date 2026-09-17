"""Named cisterns."""

from __future__ import annotations

from typing import Any


class CisternPackError(ValueError):
    pass


CISTERN = tuple(f"cs_{i:02d}" for i in range(12))


def fill(node: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in CISTERN:
        raise CisternPackError(name)
    nxt = dict(node)
    nxt["cistern"] = name
    nxt["held"] = int(nxt.get("held", 0)) + int(n)
    nxt["stored_prose"] = 0
    return nxt
