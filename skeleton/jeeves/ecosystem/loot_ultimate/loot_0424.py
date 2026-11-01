"""Loot ultimate 0424.
"""
from __future__ import annotations

ID = "loot_ultimate_0424"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 424}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
