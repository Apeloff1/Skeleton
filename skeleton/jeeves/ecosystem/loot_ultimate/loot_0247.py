"""Loot ultimate 0247.
"""
from __future__ import annotations

ID = "loot_ultimate_0247"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 247}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
