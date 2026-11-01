"""Loot ultimate 0385.
"""
from __future__ import annotations

ID = "loot_ultimate_0385"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 385}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
