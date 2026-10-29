"""Advanced biome 0048.
"""
from __future__ import annotations

BIOME = "adv_biome_0048"

def climate() -> dict:
    return {"temp": round((48 % 20) / 20, 2), "moisture": round(((48*7) % 20) / 20, 2), "wind": round((48 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 48 % 3 == 0:
        base.append("ore")
    if 48 % 5 == 0:
        base.append("crystal")
    return base
