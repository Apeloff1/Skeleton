"""Named coffers."""

from __future__ import annotations

from typing import Any


class CofferPackError(ValueError):
    pass


COFFER = tuple(f"cf_{i:02d}" for i in range(8))


def set_coffer(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COFFER:
        raise CofferPackError(name)
    nxt = dict(node)
    nxt["coffer"] = name
    nxt["stored_prose"] = 0
    return nxt
