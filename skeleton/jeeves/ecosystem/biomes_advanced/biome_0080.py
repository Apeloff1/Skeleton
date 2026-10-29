"""Advanced biome 0080.
"""
from __future__ import annotations

BIOME = "adv_biome_0080"

def climate() -> dict:
    return {"temp": round((80 % 20) / 20, 2), "moisture": round(((80*7) % 20) / 20, 2), "wind": round((80 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 80 % 3 == 0:
        base.append("ore")
    if 80 % 5 == 0:
        base.append("crystal")
    return base
