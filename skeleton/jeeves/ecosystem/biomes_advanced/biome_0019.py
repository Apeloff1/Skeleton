"""Advanced biome 0019.
"""
from __future__ import annotations

BIOME = "adv_biome_0019"

def climate() -> dict:
    return {"temp": round((19 % 20) / 20, 2), "moisture": round(((19*7) % 20) / 20, 2), "wind": round((19 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 19 % 3 == 0:
        base.append("ore")
    if 19 % 5 == 0:
        base.append("crystal")
    return base
