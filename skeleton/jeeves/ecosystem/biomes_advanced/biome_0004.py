"""Advanced biome 0004.
"""
from __future__ import annotations

BIOME = "adv_biome_0004"

def climate() -> dict:
    return {"temp": round((4 % 20) / 20, 2), "moisture": round(((4*7) % 20) / 20, 2), "wind": round((4 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 4 % 3 == 0:
        base.append("ore")
    if 4 % 5 == 0:
        base.append("crystal")
    return base
