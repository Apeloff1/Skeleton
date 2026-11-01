"""Loot ultimate 0184.
"""
from __future__ import annotations

ID = "loot_ultimate_0184"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 184}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
