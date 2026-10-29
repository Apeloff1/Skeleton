"""Advanced biome 0024.
"""
from __future__ import annotations

BIOME = "adv_biome_0024"

def climate() -> dict:
    return {"temp": round((24 % 20) / 20, 2), "moisture": round(((24*7) % 20) / 20, 2), "wind": round((24 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 24 % 3 == 0:
        base.append("ore")
    if 24 % 5 == 0:
        base.append("crystal")
    return base
