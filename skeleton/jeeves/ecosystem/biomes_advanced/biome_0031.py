"""Advanced biome 0031.
"""
from __future__ import annotations

BIOME = "adv_biome_0031"

def climate() -> dict:
    return {"temp": round((31 % 20) / 20, 2), "moisture": round(((31*7) % 20) / 20, 2), "wind": round((31 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 31 % 3 == 0:
        base.append("ore")
    if 31 % 5 == 0:
        base.append("crystal")
    return base
