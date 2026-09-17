"""Named harvests."""

from __future__ import annotations

from typing import Any


class HarvestPackError(ValueError):
    pass


HARVEST = tuple(f"hv_{i:02d}" for i in range(20))


def pick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HARVEST:
        raise HarvestPackError(name)
    nxt = dict(state)
    have = list(nxt.get("harvest") or [])
    have.append(name)
    nxt["harvest"] = have
    nxt["stored_prose"] = 0
    return nxt
