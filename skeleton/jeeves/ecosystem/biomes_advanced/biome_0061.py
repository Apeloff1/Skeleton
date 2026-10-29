"""Advanced biome 0061.
"""
from __future__ import annotations

BIOME = "adv_biome_0061"

def climate() -> dict:
    return {"temp": round((61 % 20) / 20, 2), "moisture": round(((61*7) % 20) / 20, 2), "wind": round((61 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 61 % 3 == 0:
        base.append("ore")
    if 61 % 5 == 0:
        base.append("crystal")
    return base
