"""Advanced biome 0059.
"""
from __future__ import annotations

BIOME = "adv_biome_0059"

def climate() -> dict:
    return {"temp": round((59 % 20) / 20, 2), "moisture": round(((59*7) % 20) / 20, 2), "wind": round((59 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 59 % 3 == 0:
        base.append("ore")
    if 59 % 5 == 0:
        base.append("crystal")
    return base
