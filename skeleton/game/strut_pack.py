"""Named struts."""

from __future__ import annotations

from typing import Any


class StrutPackError(ValueError):
    pass


STRUT = tuple(f"st_{i:02d}" for i in range(24))


def set_strut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STRUT:
        raise StrutPackError(name)
    nxt = dict(node)
    nxt["strut"] = name
    nxt["stress"] = max(0, min(16, int(nxt.get("stress", 0)) + (STRUT.index(name) % 3)))
    nxt["stored_prose"] = 0
    return nxt
