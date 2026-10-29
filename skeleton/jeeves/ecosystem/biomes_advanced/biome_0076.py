"""Advanced biome 0076.
"""
from __future__ import annotations

BIOME = "adv_biome_0076"

def climate() -> dict:
    return {"temp": round((76 % 20) / 20, 2), "moisture": round(((76*7) % 20) / 20, 2), "wind": round((76 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 76 % 3 == 0:
        base.append("ore")
    if 76 % 5 == 0:
        base.append("crystal")
    return base
