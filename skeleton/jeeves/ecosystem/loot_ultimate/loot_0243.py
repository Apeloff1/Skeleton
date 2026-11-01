"""Loot ultimate 0243.
"""
from __future__ import annotations

ID = "loot_ultimate_0243"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 243}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
