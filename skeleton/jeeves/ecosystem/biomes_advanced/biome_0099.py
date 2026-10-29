"""Advanced biome 0099.
"""
from __future__ import annotations

BIOME = "adv_biome_0099"

def climate() -> dict:
    return {"temp": round((99 % 20) / 20, 2), "moisture": round(((99*7) % 20) / 20, 2), "wind": round((99 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 99 % 3 == 0:
        base.append("ore")
    if 99 % 5 == 0:
        base.append("crystal")
    return base
