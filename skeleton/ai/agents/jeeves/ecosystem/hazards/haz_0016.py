"""Hazard 0016.
"""
from __future__ import annotations

HAZ = "haz_0016"

def damage(contact: bool) -> dict:
    return {"ok": True, "haz": HAZ, "damage": 5 if contact else 0}
