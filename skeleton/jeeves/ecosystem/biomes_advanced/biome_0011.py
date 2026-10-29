"""Advanced biome 0011.
"""
from __future__ import annotations

BIOME = "adv_biome_0011"

def climate() -> dict:
    return {"temp": round((11 % 20) / 20, 2), "moisture": round(((11*7) % 20) / 20, 2), "wind": round((11 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 11 % 3 == 0:
        base.append("ore")
    if 11 % 5 == 0:
        base.append("crystal")
    return base
