"""Hazard 0009.
"""
from __future__ import annotations

HAZ = "haz_0009"

def damage(contact: bool) -> dict:
    return {"ok": True, "haz": HAZ, "damage": 5 if contact else 0}
