"""Advanced biome 0037.
"""
from __future__ import annotations

BIOME = "adv_biome_0037"

def climate() -> dict:
    return {"temp": round((37 % 20) / 20, 2), "moisture": round(((37*7) % 20) / 20, 2), "wind": round((37 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 37 % 3 == 0:
        base.append("ore")
    if 37 % 5 == 0:
        base.append("crystal")
    return base
