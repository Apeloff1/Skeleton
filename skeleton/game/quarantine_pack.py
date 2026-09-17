"""Named quarantine zones."""

from __future__ import annotations

from typing import Any


class QuarantinePackError(ValueError):
    pass


QZ = tuple(f"qz_{i:02d}" for i in range(16))


def seal_zone(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in QZ:
        raise QuarantinePackError(name)
    nxt = dict(node)
    nxt["qz"] = name
    nxt["locked"] = 1
    nxt["stored_prose"] = 0
    return nxt
