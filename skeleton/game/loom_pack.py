"""Named looms."""

from __future__ import annotations

from typing import Any


class LoomPackError(ValueError):
    pass


LOOM = tuple(f"lm_{i:02d}" for i in range(12))


def set_loom(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LOOM:
        raise LoomPackError(name)
    nxt = dict(node)
    nxt["loom"] = name
    nxt["stored_prose"] = 0
    return nxt
