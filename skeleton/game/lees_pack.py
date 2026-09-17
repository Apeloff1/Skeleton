"""Named lees."""

from __future__ import annotations

from typing import Any


class LeesPackError(ValueError):
    pass


LEES = tuple(f"le_{i:02d}" for i in range(8))


def rack(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LEES:
        raise LeesPackError(name)
    nxt = dict(state)
    nxt["lees"] = name
    nxt["clear"] = 1
    nxt["stored_prose"] = 0
    return nxt
