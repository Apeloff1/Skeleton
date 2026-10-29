"""Advanced biome 0074.
"""
from __future__ import annotations

BIOME = "adv_biome_0074"

def climate() -> dict:
    return {"temp": round((74 % 20) / 20, 2), "moisture": round(((74*7) % 20) / 20, 2), "wind": round((74 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 74 % 3 == 0:
        base.append("ore")
    if 74 % 5 == 0:
        base.append("crystal")
    return base
