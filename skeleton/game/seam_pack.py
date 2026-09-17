"""Named seams."""

from __future__ import annotations

from typing import Any


class SeamPackError(ValueError):
    pass


SEAM = tuple(f"sm_{i:02d}" for i in range(16))


def set_seam(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SEAM:
        raise SeamPackError(name)
    nxt = dict(node)
    have = list(nxt.get("seam") or [])
    have.append(name)
    nxt["seam"] = have
    nxt["stored_prose"] = 0
    return nxt
