"""Advanced biome 0002.
"""
from __future__ import annotations

BIOME = "adv_biome_0002"

def climate() -> dict:
    return {"temp": round((2 % 20) / 20, 2), "moisture": round(((2*7) % 20) / 20, 2), "wind": round((2 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 2 % 3 == 0:
        base.append("ore")
    if 2 % 5 == 0:
        base.append("crystal")
    return base
