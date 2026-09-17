"""Named squeezes."""

from __future__ import annotations

from typing import Any


class SqueezePackError(ValueError):
    pass


SQUEEZE = tuple(f"sq_{i:02d}" for i in range(8))


def set_squeeze(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SQUEEZE:
        raise SqueezePackError(name)
    nxt = dict(node)
    nxt["squeeze"] = name
    nxt["stored_prose"] = 0
    return nxt
