"""Advanced biome 0009.
"""
from __future__ import annotations

BIOME = "adv_biome_0009"

def climate() -> dict:
    return {"temp": round((9 % 20) / 20, 2), "moisture": round(((9*7) % 20) / 20, 2), "wind": round((9 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 9 % 3 == 0:
        base.append("ore")
    if 9 % 5 == 0:
        base.append("crystal")
    return base
