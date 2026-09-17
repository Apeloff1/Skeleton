"""Named ribs."""

from __future__ import annotations

from typing import Any


class RibPackError(ValueError):
    pass


RIB = tuple(f"rb_{i:02d}" for i in range(16))


def set_rib(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RIB:
        raise RibPackError(name)
    nxt = dict(node)
    have = list(nxt.get("rib") or [])
    have.append(name)
    nxt["rib"] = have
    nxt["stored_prose"] = 0
    return nxt
