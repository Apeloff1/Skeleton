"""Advanced biome 0052.
"""
from __future__ import annotations

BIOME = "adv_biome_0052"

def climate() -> dict:
    return {"temp": round((52 % 20) / 20, 2), "moisture": round(((52*7) % 20) / 20, 2), "wind": round((52 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 52 % 3 == 0:
        base.append("ore")
    if 52 % 5 == 0:
        base.append("crystal")
    return base
