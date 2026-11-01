"""Loot supreme 0180.
"""
from __future__ import annotations

ID = "loot_supreme_0180"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
