"""Advanced biome 0094.
"""
from __future__ import annotations

BIOME = "adv_biome_0094"

def climate() -> dict:
    return {"temp": round((94 % 20) / 20, 2), "moisture": round(((94*7) % 20) / 20, 2), "wind": round((94 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 94 % 3 == 0:
        base.append("ore")
    if 94 % 5 == 0:
        base.append("crystal")
    return base
