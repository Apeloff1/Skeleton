"""Advanced biome 0040.
"""
from __future__ import annotations

BIOME = "adv_biome_0040"

def climate() -> dict:
    return {"temp": round((40 % 20) / 20, 2), "moisture": round(((40*7) % 20) / 20, 2), "wind": round((40 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 40 % 3 == 0:
        base.append("ore")
    if 40 % 5 == 0:
        base.append("crystal")
    return base
