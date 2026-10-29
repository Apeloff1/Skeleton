"""Advanced biome 0045.
"""
from __future__ import annotations

BIOME = "adv_biome_0045"

def climate() -> dict:
    return {"temp": round((45 % 20) / 20, 2), "moisture": round(((45*7) % 20) / 20, 2), "wind": round((45 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 45 % 3 == 0:
        base.append("ore")
    if 45 % 5 == 0:
        base.append("crystal")
    return base
