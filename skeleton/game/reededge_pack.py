"""Named reeded edges."""

from __future__ import annotations

from typing import Any


class ReededgePackError(ValueError):
    pass


REED = tuple(f"re_{i:02d}" for i in range(8))


def set_reed(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in REED:
        raise ReededgePackError(name)
    nxt = dict(state)
    nxt["reededge"] = name
    nxt["stored_prose"] = 0
    return nxt
