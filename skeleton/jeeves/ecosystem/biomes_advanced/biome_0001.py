"""Advanced biome 0001.
"""
from __future__ import annotations

BIOME = "adv_biome_0001"

def climate() -> dict:
    return {"temp": round((1 % 20) / 20, 2), "moisture": round(((1*7) % 20) / 20, 2), "wind": round((1 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 1 % 3 == 0:
        base.append("ore")
    if 1 % 5 == 0:
        base.append("crystal")
    return base
