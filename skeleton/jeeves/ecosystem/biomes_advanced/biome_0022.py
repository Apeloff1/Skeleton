"""Advanced biome 0022.
"""
from __future__ import annotations

BIOME = "adv_biome_0022"

def climate() -> dict:
    return {"temp": round((22 % 20) / 20, 2), "moisture": round(((22*7) % 20) / 20, 2), "wind": round((22 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 22 % 3 == 0:
        base.append("ore")
    if 22 % 5 == 0:
        base.append("crystal")
    return base
