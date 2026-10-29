"""Advanced biome 0079.
"""
from __future__ import annotations

BIOME = "adv_biome_0079"

def climate() -> dict:
    return {"temp": round((79 % 20) / 20, 2), "moisture": round(((79*7) % 20) / 20, 2), "wind": round((79 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 79 % 3 == 0:
        base.append("ore")
    if 79 % 5 == 0:
        base.append("crystal")
    return base
