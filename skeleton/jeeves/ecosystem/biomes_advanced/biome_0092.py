"""Advanced biome 0092.
"""
from __future__ import annotations

BIOME = "adv_biome_0092"

def climate() -> dict:
    return {"temp": round((92 % 20) / 20, 2), "moisture": round(((92*7) % 20) / 20, 2), "wind": round((92 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 92 % 3 == 0:
        base.append("ore")
    if 92 % 5 == 0:
        base.append("crystal")
    return base
