"""Advanced biome 0026.
"""
from __future__ import annotations

BIOME = "adv_biome_0026"

def climate() -> dict:
    return {"temp": round((26 % 20) / 20, 2), "moisture": round(((26*7) % 20) / 20, 2), "wind": round((26 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 26 % 3 == 0:
        base.append("ore")
    if 26 % 5 == 0:
        base.append("crystal")
    return base
