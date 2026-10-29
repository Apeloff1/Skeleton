"""Advanced biome 0029.
"""
from __future__ import annotations

BIOME = "adv_biome_0029"

def climate() -> dict:
    return {"temp": round((29 % 20) / 20, 2), "moisture": round(((29*7) % 20) / 20, 2), "wind": round((29 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 29 % 3 == 0:
        base.append("ore")
    if 29 % 5 == 0:
        base.append("crystal")
    return base
