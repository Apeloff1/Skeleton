"""Advanced biome 0018.
"""
from __future__ import annotations

BIOME = "adv_biome_0018"

def climate() -> dict:
    return {"temp": round((18 % 20) / 20, 2), "moisture": round(((18*7) % 20) / 20, 2), "wind": round((18 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 18 % 3 == 0:
        base.append("ore")
    if 18 % 5 == 0:
        base.append("crystal")
    return base
