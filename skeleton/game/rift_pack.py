"""Named rifts."""

from __future__ import annotations

from typing import Any


class RiftPackError(ValueError):
    pass


RIFT = tuple(f"rf_{i:02d}" for i in range(16))


def open_rift(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RIFT:
        raise RiftPackError(name)
    nxt = dict(node)
    nxt["rift"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
