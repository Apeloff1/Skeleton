"""Advanced biome 0034.
"""
from __future__ import annotations

BIOME = "adv_biome_0034"

def climate() -> dict:
    return {"temp": round((34 % 20) / 20, 2), "moisture": round(((34*7) % 20) / 20, 2), "wind": round((34 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 34 % 3 == 0:
        base.append("ore")
    if 34 % 5 == 0:
        base.append("crystal")
    return base
