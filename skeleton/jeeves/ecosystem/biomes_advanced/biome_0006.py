"""Advanced biome 0006.
"""
from __future__ import annotations

BIOME = "adv_biome_0006"

def climate() -> dict:
    return {"temp": round((6 % 20) / 20, 2), "moisture": round(((6*7) % 20) / 20, 2), "wind": round((6 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 6 % 3 == 0:
        base.append("ore")
    if 6 % 5 == 0:
        base.append("crystal")
    return base
