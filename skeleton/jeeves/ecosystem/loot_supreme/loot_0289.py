"""Loot supreme 0289.
"""
from __future__ import annotations

ID = "loot_supreme_0289"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 289}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
