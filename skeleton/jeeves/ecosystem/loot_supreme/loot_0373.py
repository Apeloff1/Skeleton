"""Loot supreme 0373.
"""
from __future__ import annotations

ID = "loot_supreme_0373"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 373}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
