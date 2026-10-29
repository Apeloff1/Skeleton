"""Advanced biome 0017.
"""
from __future__ import annotations

BIOME = "adv_biome_0017"

def climate() -> dict:
    return {"temp": round((17 % 20) / 20, 2), "moisture": round(((17*7) % 20) / 20, 2), "wind": round((17 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 17 % 3 == 0:
        base.append("ore")
    if 17 % 5 == 0:
        base.append("crystal")
    return base
