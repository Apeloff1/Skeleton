"""Advanced biome 0023.
"""
from __future__ import annotations

BIOME = "adv_biome_0023"

def climate() -> dict:
    return {"temp": round((23 % 20) / 20, 2), "moisture": round(((23*7) % 20) / 20, 2), "wind": round((23 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 23 % 3 == 0:
        base.append("ore")
    if 23 % 5 == 0:
        base.append("crystal")
    return base
