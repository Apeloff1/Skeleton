"""Named trusses."""

from __future__ import annotations

from typing import Any


class TrussPackError(ValueError):
    pass


TRUSS = tuple(f"tr_{i:02d}" for i in range(20))


def span(node: dict[str, Any], name: str, a: str, b: str) -> dict[str, Any]:
    if name not in TRUSS:
        raise TrussPackError(name)
    nxt = dict(node)
    nxt["truss"] = name
    nxt["a"] = a
    nxt["b"] = b
    nxt["stored_prose"] = 0
    return nxt
