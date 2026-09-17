"""Named wards. Spend coil."""

from __future__ import annotations

from typing import Any


class WardPackError(ValueError):
    pass


WARDS = tuple(f"wd_{i:02d}" for i in range(16))


def raise_ward(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WARDS:
        raise WardPackError(name)
    nxt = dict(state)
    if int(nxt.get("coil", 0)) < 1:
        raise WardPackError("coil")
    nxt["coil"] = int(nxt.get("coil", 0)) - 1
    nxt["ward"] = name
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) - 2)
    nxt["stored_prose"] = 0
    return nxt
