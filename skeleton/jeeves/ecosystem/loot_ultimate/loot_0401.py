"""Loot ultimate 0401.
"""
from __future__ import annotations

ID = "loot_ultimate_0401"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 401}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
