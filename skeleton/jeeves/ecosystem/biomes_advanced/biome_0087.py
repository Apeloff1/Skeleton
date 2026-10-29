"""Advanced biome 0087.
"""
from __future__ import annotations

BIOME = "adv_biome_0087"

def climate() -> dict:
    return {"temp": round((87 % 20) / 20, 2), "moisture": round(((87*7) % 20) / 20, 2), "wind": round((87 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 87 % 3 == 0:
        base.append("ore")
    if 87 % 5 == 0:
        base.append("crystal")
    return base
