"""Loot ultimate 0027.
"""
from __future__ import annotations

ID = "loot_ultimate_0027"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
