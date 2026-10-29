"""Advanced biome 0086.
"""
from __future__ import annotations

BIOME = "adv_biome_0086"

def climate() -> dict:
    return {"temp": round((86 % 20) / 20, 2), "moisture": round(((86*7) % 20) / 20, 2), "wind": round((86 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 86 % 3 == 0:
        base.append("ore")
    if 86 % 5 == 0:
        base.append("crystal")
    return base
