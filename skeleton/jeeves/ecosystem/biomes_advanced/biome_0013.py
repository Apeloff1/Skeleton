"""Advanced biome 0013.
"""
from __future__ import annotations

BIOME = "adv_biome_0013"

def climate() -> dict:
    return {"temp": round((13 % 20) / 20, 2), "moisture": round(((13*7) % 20) / 20, 2), "wind": round((13 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 13 % 3 == 0:
        base.append("ore")
    if 13 % 5 == 0:
        base.append("crystal")
    return base
