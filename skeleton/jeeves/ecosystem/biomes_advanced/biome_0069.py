"""Advanced biome 0069.
"""
from __future__ import annotations

BIOME = "adv_biome_0069"

def climate() -> dict:
    return {"temp": round((69 % 20) / 20, 2), "moisture": round(((69*7) % 20) / 20, 2), "wind": round((69 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 69 % 3 == 0:
        base.append("ore")
    if 69 % 5 == 0:
        base.append("crystal")
    return base
