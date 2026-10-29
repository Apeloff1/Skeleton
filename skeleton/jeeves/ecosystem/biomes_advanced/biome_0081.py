"""Advanced biome 0081.
"""
from __future__ import annotations

BIOME = "adv_biome_0081"

def climate() -> dict:
    return {"temp": round((81 % 20) / 20, 2), "moisture": round(((81*7) % 20) / 20, 2), "wind": round((81 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 81 % 3 == 0:
        base.append("ore")
    if 81 % 5 == 0:
        base.append("crystal")
    return base
