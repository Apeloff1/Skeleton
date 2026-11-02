"""Loot eco_supreme 0562.
"""
from __future__ import annotations

ID = "loot_eco_supreme_0562"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 562}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
