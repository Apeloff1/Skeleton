"""Advanced biome 0063.
"""
from __future__ import annotations

BIOME = "adv_biome_0063"

def climate() -> dict:
    return {"temp": round((63 % 20) / 20, 2), "moisture": round(((63*7) % 20) / 20, 2), "wind": round((63 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 63 % 3 == 0:
        base.append("ore")
    if 63 % 5 == 0:
        base.append("crystal")
    return base
