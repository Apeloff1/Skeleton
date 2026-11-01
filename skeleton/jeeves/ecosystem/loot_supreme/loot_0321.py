"""Loot supreme 0321.
"""
from __future__ import annotations

ID = "loot_supreme_0321"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 321}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
