"""Wave-4 cell ticks. Extract once."""

from __future__ import annotations

from typing import Any


class CellWaveError(ValueError):
    pass


CELLS = tuple(f"cell_{i:02d}" for i in range(16))


def tick(state: dict[str, Any], name: str, verb: str) -> dict[str, Any]:
    if name not in CELLS:
        raise CellWaveError(name)
    nxt = dict(state)
    nxt["cell"] = name
    if verb == "heat":
        nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    elif verb == "wait":
        nxt["sleep"] = int(nxt.get("sleep", 0)) + 1
    elif verb == "extract":
        if int(nxt.get("extracted", 0)) != 0:
            raise CellWaveError("twice")
        if int(nxt.get("heat", 0)) < 8:
            raise CellWaveError("cold")
        nxt["extracted"] = 1
        nxt["warp_count"] = 1
    nxt["stored_prose"] = 0
    return nxt
