"""Named aisles."""

from __future__ import annotations

from typing import Any


class AislePackError(ValueError):
    pass


AISLE = tuple(f"ai_{i:02d}" for i in range(8))


def set_aisle(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in AISLE:
        raise AislePackError(name)
    nxt = dict(node)
    nxt["aisle"] = name
    nxt["stored_prose"] = 0
    return nxt
