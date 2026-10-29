"""Advanced biome 0000.
"""
from __future__ import annotations

BIOME = "adv_biome_0000"

def climate() -> dict:
    return {"temp": round((0 % 20) / 20, 2), "moisture": round(((0*7) % 20) / 20, 2), "wind": round((0 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 0 % 3 == 0:
        base.append("ore")
    if 0 % 5 == 0:
        base.append("crystal")
    return base
