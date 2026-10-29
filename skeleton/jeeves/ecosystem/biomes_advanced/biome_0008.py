"""Advanced biome 0008.
"""
from __future__ import annotations

BIOME = "adv_biome_0008"

def climate() -> dict:
    return {"temp": round((8 % 20) / 20, 2), "moisture": round(((8*7) % 20) / 20, 2), "wind": round((8 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 8 % 3 == 0:
        base.append("ore")
    if 8 % 5 == 0:
        base.append("crystal")
    return base
