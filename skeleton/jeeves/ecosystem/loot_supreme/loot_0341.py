"""Loot supreme 0341.
"""
from __future__ import annotations

ID = "loot_supreme_0341"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 341}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
