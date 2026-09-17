"""Named stash bins."""

from __future__ import annotations

from typing import Any


class BinPackError(ValueError):
    pass


BINS = tuple(f"bin_{i:02d}" for i in range(24))


def put(state: dict[str, Any], name: str, slot: str, n: int = 1) -> dict[str, Any]:
    if name not in BINS:
        raise BinPackError(name)
    nxt = dict(state)
    bins = dict(nxt.get("bin") or {})
    cell = dict(bins.get(name) or {})
    cell[slot] = int(cell.get(slot, 0)) + int(n)
    bins[name] = cell
    nxt["bin"] = bins
    nxt["stored_prose"] = 0
    return nxt
