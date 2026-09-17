"""Named glass panes."""

from __future__ import annotations

from typing import Any


class GlassPackError(ValueError):
    pass


GLASS = tuple(f"gl_{i:02d}" for i in range(16))


def set_pane(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GLASS:
        raise GlassPackError(name)
    nxt = dict(node)
    have = list(nxt.get("glass") or [])
    if name not in have:
        have.append(name)
    nxt["glass"] = have
    nxt["stored_prose"] = 0
    return nxt
