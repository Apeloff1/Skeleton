"""Named bonds to agents."""

from __future__ import annotations

from typing import Any


class BondPackError(ValueError):
    pass


BONDS = tuple(f"bn_{i:02d}" for i in range(20))


def tie(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in BONDS:
        raise BondPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("bond") or {})
    cur[name] = who
    nxt["bond"] = cur
    nxt["stored_prose"] = 0
    return nxt
