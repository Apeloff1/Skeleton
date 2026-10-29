"""Advanced biome 0088.
"""
from __future__ import annotations

BIOME = "adv_biome_0088"

def climate() -> dict:
    return {"temp": round((88 % 20) / 20, 2), "moisture": round(((88*7) % 20) / 20, 2), "wind": round((88 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 88 % 3 == 0:
        base.append("ore")
    if 88 % 5 == 0:
        base.append("crystal")
    return base
