"""Advanced biome 0014.
"""
from __future__ import annotations

BIOME = "adv_biome_0014"

def climate() -> dict:
    return {"temp": round((14 % 20) / 20, 2), "moisture": round(((14*7) % 20) / 20, 2), "wind": round((14 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 14 % 3 == 0:
        base.append("ore")
    if 14 % 5 == 0:
        base.append("crystal")
    return base
