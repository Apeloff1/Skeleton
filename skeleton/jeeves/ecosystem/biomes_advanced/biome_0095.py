"""Advanced biome 0095.
"""
from __future__ import annotations

BIOME = "adv_biome_0095"

def climate() -> dict:
    return {"temp": round((95 % 20) / 20, 2), "moisture": round(((95*7) % 20) / 20, 2), "wind": round((95 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 95 % 3 == 0:
        base.append("ore")
    if 95 % 5 == 0:
        base.append("crystal")
    return base
