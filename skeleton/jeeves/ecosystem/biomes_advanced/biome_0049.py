"""Advanced biome 0049.
"""
from __future__ import annotations

BIOME = "adv_biome_0049"

def climate() -> dict:
    return {"temp": round((49 % 20) / 20, 2), "moisture": round(((49*7) % 20) / 20, 2), "wind": round((49 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 49 % 3 == 0:
        base.append("ore")
    if 49 % 5 == 0:
        base.append("crystal")
    return base
