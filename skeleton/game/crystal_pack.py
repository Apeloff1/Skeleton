"""Named salt crystals."""

from __future__ import annotations

from typing import Any


class CrystalPackError(ValueError):
    pass


CRYSTAL = tuple(f"cr_{i:02d}" for i in range(16))


def form(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CRYSTAL:
        raise CrystalPackError(name)
    nxt = dict(state)
    have = list(nxt.get("crystal") or [])
    have.append(name)
    nxt["crystal"] = have
    nxt["stored_prose"] = 0
    return nxt
