"""Advanced biome 0051.
"""
from __future__ import annotations

BIOME = "adv_biome_0051"

def climate() -> dict:
    return {"temp": round((51 % 20) / 20, 2), "moisture": round(((51*7) % 20) / 20, 2), "wind": round((51 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 51 % 3 == 0:
        base.append("ore")
    if 51 % 5 == 0:
        base.append("crystal")
    return base
