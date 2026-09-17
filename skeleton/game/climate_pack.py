"""Climate fronts. Phase table."""

from __future__ import annotations

from typing import Any


class ClimatePackError(ValueError):
    pass


PHASE = {
    "vent": (-2, 0),
    "ash": (-1, 1),
    "fog": (0, 2),
    "chill": (1, 0),
    "heat": (2, 0),
    "storm": (1, 2),
    "still": (0, 0),
    "pulse": (2, 1),
    "bleed": (-1, 1),
    "ward": (-2, 0),
    "dream": (0, 2),
    "lock": (0, 0),
    "shaft": (1, 0),
    "crowd": (1, 1),
    "quiet": (-1, 0),
    "extract": (0, 0),
}


def run(nodes: list[dict[str, Any]], ticks: int, phase: str) -> dict[str, Any]:
    if phase not in PHASE:
        raise ClimatePackError(phase)
    dh, df = PHASE[phase]
    cur = [dict(n) for n in nodes]
    tokens = 0
    for t in range(int(ticks)):
        nxt = []
        for node in cur:
            row = dict(node)
            row["heat"] = max(0, min(16, int(row.get("heat", 0)) + dh + (t % 3) - 1))
            row["fog"] = max(0, min(8, int(row.get("fog", 0)) + df - 1))
            row["stored_prose"] = 0
            nxt.append(row)
        cur = nxt
        tokens += 1
    peak = max((int(n.get("heat", 0)) for n in cur), default=0)
    return {"kind": "climate_pack", "phase": phase, "peak": peak, "tokens": tokens, "nodes": cur, "stored_prose": 0}
