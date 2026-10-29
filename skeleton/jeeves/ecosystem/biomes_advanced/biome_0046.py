"""Advanced biome 0046.
"""
from __future__ import annotations

BIOME = "adv_biome_0046"

def climate() -> dict:
    return {"temp": round((46 % 20) / 20, 2), "moisture": round(((46*7) % 20) / 20, 2), "wind": round((46 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 46 % 3 == 0:
        base.append("ore")
    if 46 % 5 == 0:
        base.append("crystal")
    return base
