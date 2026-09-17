"""Named salt pans."""

from __future__ import annotations

from typing import Any


class PanPackError(ValueError):
    pass


PAN = tuple(f"pn_{i:02d}" for i in range(12))


def set_pan(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PAN:
        raise PanPackError(name)
    nxt = dict(node)
    nxt["pan"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
