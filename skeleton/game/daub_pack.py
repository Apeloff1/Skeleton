"""Named daub lots."""

from __future__ import annotations

from typing import Any


class DaubPackError(ValueError):
    pass


DAUB = tuple(f"db_{i:02d}" for i in range(12))


def smear(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DAUB:
        raise DaubPackError(name)
    nxt = dict(node)
    nxt["daub"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
