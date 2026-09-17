"""Named hay lofts."""

from __future__ import annotations

from typing import Any


class HayloftPackError(ValueError):
    pass


LOFT = tuple(f"hl_{i:02d}" for i in range(8))


def set_loft(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LOFT:
        raise HayloftPackError(name)
    nxt = dict(node)
    nxt["hayloft"] = name
    nxt["stored_prose"] = 0
    return nxt
