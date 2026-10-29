"""Advanced biome 0021.
"""
from __future__ import annotations

BIOME = "adv_biome_0021"

def climate() -> dict:
    return {"temp": round((21 % 20) / 20, 2), "moisture": round(((21*7) % 20) / 20, 2), "wind": round((21 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 21 % 3 == 0:
        base.append("ore")
    if 21 % 5 == 0:
        base.append("crystal")
    return base
