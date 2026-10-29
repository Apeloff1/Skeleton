"""Garden 0015.
"""
from __future__ import annotations

GARDEN = "garden_0015"

def plant(seed: str) -> dict:
    if not seed:
        return {"ok": False, "reason": "no_seed"}
    return {"ok": True, "garden": GARDEN, "seed": seed}
