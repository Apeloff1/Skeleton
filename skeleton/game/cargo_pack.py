"""Named cargo lots."""

from __future__ import annotations

from typing import Any


class CargoPackError(ValueError):
    pass


LOTS = tuple(f"cg_{i:02d}" for i in range(20))


def load(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LOTS:
        raise CargoPackError(name)
    nxt = dict(state)
    lots = list(nxt.get("cargo") or [])
    lots.append(name)
    nxt["cargo"] = lots
    nxt["mass"] = int(nxt.get("mass", 0)) + 1 + (LOTS.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
