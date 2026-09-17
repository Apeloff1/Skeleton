"""Named dovetails."""

from __future__ import annotations

from typing import Any


class DovetailPackError(ValueError):
    pass


DOVETAIL = tuple(f"dv_{i:02d}" for i in range(12))


def cut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DOVETAIL:
        raise DovetailPackError(name)
    nxt = dict(node)
    nxt["dovetail"] = name
    nxt["pins"] = int(nxt.get("pins", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
