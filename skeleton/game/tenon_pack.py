"""Named tenons."""

from __future__ import annotations

from typing import Any


class TenonPackError(ValueError):
    pass


TENON = tuple(f"tn_{i:02d}" for i in range(16))


def cut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TENON:
        raise TenonPackError(name)
    nxt = dict(node)
    nxt["tenon"] = name
    nxt["stored_prose"] = 0
    return nxt
