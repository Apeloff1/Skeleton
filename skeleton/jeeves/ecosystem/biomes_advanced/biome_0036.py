"""Advanced biome 0036.
"""
from __future__ import annotations

BIOME = "adv_biome_0036"

def climate() -> dict:
    return {"temp": round((36 % 20) / 20, 2), "moisture": round(((36*7) % 20) / 20, 2), "wind": round((36 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 36 % 3 == 0:
        base.append("ore")
    if 36 % 5 == 0:
        base.append("crystal")
    return base
