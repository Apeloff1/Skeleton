"""Loot ultimate 0262.
"""
from __future__ import annotations

ID = "loot_ultimate_0262"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 262}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
