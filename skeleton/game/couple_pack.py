"""Named couplings."""

from __future__ import annotations

from typing import Any


class CouplePackError(ValueError):
    pass


COUPLE = tuple(f"cp_{i:02d}" for i in range(20))


def lock(state: dict[str, Any], name: str, a: str, b: str) -> dict[str, Any]:
    if name not in COUPLE:
        raise CouplePackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("couple") or {})
    cur[name] = (a, b)
    nxt["couple"] = cur
    nxt["stored_prose"] = 0
    return nxt
