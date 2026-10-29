"""Advanced biome 0054.
"""
from __future__ import annotations

BIOME = "adv_biome_0054"

def climate() -> dict:
    return {"temp": round((54 % 20) / 20, 2), "moisture": round(((54*7) % 20) / 20, 2), "wind": round((54 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 54 % 3 == 0:
        base.append("ore")
    if 54 % 5 == 0:
        base.append("crystal")
    return base
