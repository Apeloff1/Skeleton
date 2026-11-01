"""Loot ultimate 0245.
"""
from __future__ import annotations

ID = "loot_ultimate_0245"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 245}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
