"""Advanced biome 0020.
"""
from __future__ import annotations

BIOME = "adv_biome_0020"

def climate() -> dict:
    return {"temp": round((20 % 20) / 20, 2), "moisture": round(((20*7) % 20) / 20, 2), "wind": round((20 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 20 % 3 == 0:
        base.append("ore")
    if 20 % 5 == 0:
        base.append("crystal")
    return base
