"""Advanced biome 0055.
"""
from __future__ import annotations

BIOME = "adv_biome_0055"

def climate() -> dict:
    return {"temp": round((55 % 20) / 20, 2), "moisture": round(((55*7) % 20) / 20, 2), "wind": round((55 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 55 % 3 == 0:
        base.append("ore")
    if 55 % 5 == 0:
        base.append("crystal")
    return base
