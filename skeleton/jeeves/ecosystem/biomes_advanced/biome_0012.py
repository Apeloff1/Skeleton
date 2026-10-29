"""Advanced biome 0012.
"""
from __future__ import annotations

BIOME = "adv_biome_0012"

def climate() -> dict:
    return {"temp": round((12 % 20) / 20, 2), "moisture": round(((12*7) % 20) / 20, 2), "wind": round((12 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 12 % 3 == 0:
        base.append("ore")
    if 12 % 5 == 0:
        base.append("crystal")
    return base
