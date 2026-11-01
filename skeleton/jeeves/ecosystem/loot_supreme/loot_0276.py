"""Loot supreme 0276.
"""
from __future__ import annotations

ID = "loot_supreme_0276"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 276}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
