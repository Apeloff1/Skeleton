"""Loot supreme 0201.
"""
from __future__ import annotations

ID = "loot_supreme_0201"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 201}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
