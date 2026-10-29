"""Advanced biome 0096.
"""
from __future__ import annotations

BIOME = "adv_biome_0096"

def climate() -> dict:
    return {"temp": round((96 % 20) / 20, 2), "moisture": round(((96*7) % 20) / 20, 2), "wind": round((96 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 96 % 3 == 0:
        base.append("ore")
    if 96 % 5 == 0:
        base.append("crystal")
    return base
