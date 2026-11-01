"""Loot ultimate 0379.
"""
from __future__ import annotations

ID = "loot_ultimate_0379"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 379}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
