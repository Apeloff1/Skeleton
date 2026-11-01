"""Loot supreme 0215.
"""
from __future__ import annotations

ID = "loot_supreme_0215"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 215}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
