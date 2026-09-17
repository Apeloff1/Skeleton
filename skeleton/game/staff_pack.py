"""Named leveling staffs."""

from __future__ import annotations

from typing import Any


class StaffPackError(ValueError):
    pass


STAFF = tuple(f"sf_{i:02d}" for i in range(12))


def read(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in STAFF:
        raise StaffPackError(name)
    nxt = dict(state)
    nxt["staff"] = name
    nxt["level"] = int(n)
    nxt["stored_prose"] = 0
    return nxt
