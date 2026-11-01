"""Loot ultimate 0390.
"""
from __future__ import annotations

ID = "loot_ultimate_0390"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 390}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
