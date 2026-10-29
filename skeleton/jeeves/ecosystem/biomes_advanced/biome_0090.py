"""Advanced biome 0090.
"""
from __future__ import annotations

BIOME = "adv_biome_0090"

def climate() -> dict:
    return {"temp": round((90 % 20) / 20, 2), "moisture": round(((90*7) % 20) / 20, 2), "wind": round((90 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 90 % 3 == 0:
        base.append("ore")
    if 90 % 5 == 0:
        base.append("crystal")
    return base
