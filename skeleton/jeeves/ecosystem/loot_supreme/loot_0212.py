"""Loot supreme 0212.
"""
from __future__ import annotations

ID = "loot_supreme_0212"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 212}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
