"""Loot ultimate 0418.
"""
from __future__ import annotations

ID = "loot_ultimate_0418"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 418}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
