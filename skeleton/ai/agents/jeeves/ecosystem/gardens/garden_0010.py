"""Garden 0010.
"""
from __future__ import annotations

GARDEN = "garden_0010"

def plant(seed: str) -> dict:
    if not seed:
        return {"ok": False, "reason": "no_seed"}
    return {"ok": True, "garden": GARDEN, "seed": seed}
