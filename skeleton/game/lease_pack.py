"""Named room leases."""

from __future__ import annotations

from typing import Any


class LeasePackError(ValueError):
    pass


LEASES = tuple(f"ls_{i:02d}" for i in range(16))


def take(state: dict[str, Any], name: str, room: str) -> dict[str, Any]:
    if name not in LEASES:
        raise LeasePackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("lease") or {})
    cur[name] = room
    nxt["lease"] = cur
    nxt["stored_prose"] = 0
    return nxt
