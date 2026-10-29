"""Advanced biome 0075.
"""
from __future__ import annotations

BIOME = "adv_biome_0075"

def climate() -> dict:
    return {"temp": round((75 % 20) / 20, 2), "moisture": round(((75*7) % 20) / 20, 2), "wind": round((75 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 75 % 3 == 0:
        base.append("ore")
    if 75 % 5 == 0:
        base.append("crystal")
    return base
