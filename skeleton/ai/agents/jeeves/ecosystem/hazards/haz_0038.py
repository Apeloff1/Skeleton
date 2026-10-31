"""Hazard 0038.
"""
from __future__ import annotations

HAZ = "haz_0038"

def damage(contact: bool) -> dict:
    return {"ok": True, "haz": HAZ, "damage": 5 if contact else 0}
