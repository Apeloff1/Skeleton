"""Advanced biome 0030.
"""
from __future__ import annotations

BIOME = "adv_biome_0030"

def climate() -> dict:
    return {"temp": round((30 % 20) / 20, 2), "moisture": round(((30*7) % 20) / 20, 2), "wind": round((30 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 30 % 3 == 0:
        base.append("ore")
    if 30 % 5 == 0:
        base.append("crystal")
    return base
