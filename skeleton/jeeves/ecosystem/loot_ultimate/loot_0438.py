"""Loot ultimate 0438.
"""
from __future__ import annotations

ID = "loot_ultimate_0438"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 438}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
