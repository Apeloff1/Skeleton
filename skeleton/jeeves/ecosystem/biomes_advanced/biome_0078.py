"""Advanced biome 0078.
"""
from __future__ import annotations

BIOME = "adv_biome_0078"

def climate() -> dict:
    return {"temp": round((78 % 20) / 20, 2), "moisture": round(((78*7) % 20) / 20, 2), "wind": round((78 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 78 % 3 == 0:
        base.append("ore")
    if 78 % 5 == 0:
        base.append("crystal")
    return base
