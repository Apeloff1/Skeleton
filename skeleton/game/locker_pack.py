"""Named lockers."""

from __future__ import annotations

from typing import Any


class LockerPackError(ValueError):
    pass


LOCKER = tuple(f"lk_{i:02d}" for i in range(20))


def stow(state: dict[str, Any], name: str, slot: str, n: int = 1) -> dict[str, Any]:
    if name not in LOCKER:
        raise LockerPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("locker") or {})
    cell = dict(cur.get(name) or {})
    cell[slot] = int(cell.get(slot, 0)) + int(n)
    cur[name] = cell
    nxt["locker"] = cur
    nxt["stored_prose"] = 0
    return nxt
