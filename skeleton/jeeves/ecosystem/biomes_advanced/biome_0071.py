"""Advanced biome 0071.
"""
from __future__ import annotations

BIOME = "adv_biome_0071"

def climate() -> dict:
    return {"temp": round((71 % 20) / 20, 2), "moisture": round(((71*7) % 20) / 20, 2), "wind": round((71 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 71 % 3 == 0:
        base.append("ore")
    if 71 % 5 == 0:
        base.append("crystal")
    return base
