"""Advanced biome 0072.
"""
from __future__ import annotations

BIOME = "adv_biome_0072"

def climate() -> dict:
    return {"temp": round((72 % 20) / 20, 2), "moisture": round(((72*7) % 20) / 20, 2), "wind": round((72 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 72 % 3 == 0:
        base.append("ore")
    if 72 % 5 == 0:
        base.append("crystal")
    return base
