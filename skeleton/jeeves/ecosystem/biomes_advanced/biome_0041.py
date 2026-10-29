"""Advanced biome 0041.
"""
from __future__ import annotations

BIOME = "adv_biome_0041"

def climate() -> dict:
    return {"temp": round((41 % 20) / 20, 2), "moisture": round(((41*7) % 20) / 20, 2), "wind": round((41 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 41 % 3 == 0:
        base.append("ore")
    if 41 % 5 == 0:
        base.append("crystal")
    return base
