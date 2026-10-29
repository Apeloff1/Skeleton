"""Advanced biome 0015.
"""
from __future__ import annotations

BIOME = "adv_biome_0015"

def climate() -> dict:
    return {"temp": round((15 % 20) / 20, 2), "moisture": round(((15*7) % 20) / 20, 2), "wind": round((15 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 15 % 3 == 0:
        base.append("ore")
    if 15 % 5 == 0:
        base.append("crystal")
    return base
