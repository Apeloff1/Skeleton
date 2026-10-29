"""Advanced biome 0089.
"""
from __future__ import annotations

BIOME = "adv_biome_0089"

def climate() -> dict:
    return {"temp": round((89 % 20) / 20, 2), "moisture": round(((89*7) % 20) / 20, 2), "wind": round((89 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 89 % 3 == 0:
        base.append("ore")
    if 89 % 5 == 0:
        base.append("crystal")
    return base
