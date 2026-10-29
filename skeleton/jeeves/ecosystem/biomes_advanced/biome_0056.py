"""Advanced biome 0056.
"""
from __future__ import annotations

BIOME = "adv_biome_0056"

def climate() -> dict:
    return {"temp": round((56 % 20) / 20, 2), "moisture": round(((56*7) % 20) / 20, 2), "wind": round((56 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 56 % 3 == 0:
        base.append("ore")
    if 56 % 5 == 0:
        base.append("crystal")
    return base
