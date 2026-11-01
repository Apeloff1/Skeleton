"""Loot ultra_max 0273.
"""
from __future__ import annotations

ID = "loot_ultra_max_0273"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
