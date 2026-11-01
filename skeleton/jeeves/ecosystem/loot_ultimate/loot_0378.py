"""Loot ultimate 0378.
"""
from __future__ import annotations

ID = "loot_ultimate_0378"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 378}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
