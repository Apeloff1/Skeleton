"""Advanced biome 0027.
"""
from __future__ import annotations

BIOME = "adv_biome_0027"

def climate() -> dict:
    return {"temp": round((27 % 20) / 20, 2), "moisture": round(((27*7) % 20) / 20, 2), "wind": round((27 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 27 % 3 == 0:
        base.append("ore")
    if 27 % 5 == 0:
        base.append("crystal")
    return base
