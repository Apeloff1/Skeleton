"""Advanced biome 0025.
"""
from __future__ import annotations

BIOME = "adv_biome_0025"

def climate() -> dict:
    return {"temp": round((25 % 20) / 20, 2), "moisture": round(((25*7) % 20) / 20, 2), "wind": round((25 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 25 % 3 == 0:
        base.append("ore")
    if 25 % 5 == 0:
        base.append("crystal")
    return base
