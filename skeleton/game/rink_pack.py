"""Named rink tiles. Occupancy jam/spill."""

from __future__ import annotations


class RinkPackError(ValueError):
    pass


RINK = tuple(f"rk_{i:02d}" for i in range(16))


def jam(occ: dict[str, int], name: str) -> dict[str, int]:
    if name not in RINK:
        raise RinkPackError(name)
    nxt = dict(occ)
    nxt[name] = int(nxt.get(name, 0)) + 1
    return nxt


def spill(occ: dict[str, int], name: str) -> dict[str, int]:
    if name not in RINK:
        raise RinkPackError(name)
    nxt = dict(occ)
    nxt[name] = max(0, int(nxt.get(name, 0)) - 1)
    return nxt
