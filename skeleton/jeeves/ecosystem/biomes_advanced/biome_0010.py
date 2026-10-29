"""Advanced biome 0010.
"""
from __future__ import annotations

BIOME = "adv_biome_0010"

def climate() -> dict:
    return {"temp": round((10 % 20) / 20, 2), "moisture": round(((10*7) % 20) / 20, 2), "wind": round((10 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 10 % 3 == 0:
        base.append("ore")
    if 10 % 5 == 0:
        base.append("crystal")
    return base
