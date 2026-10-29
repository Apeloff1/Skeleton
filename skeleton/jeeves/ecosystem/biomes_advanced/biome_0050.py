"""Advanced biome 0050.
"""
from __future__ import annotations

BIOME = "adv_biome_0050"

def climate() -> dict:
    return {"temp": round((50 % 20) / 20, 2), "moisture": round(((50*7) % 20) / 20, 2), "wind": round((50 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 50 % 3 == 0:
        base.append("ore")
    if 50 % 5 == 0:
        base.append("crystal")
    return base
