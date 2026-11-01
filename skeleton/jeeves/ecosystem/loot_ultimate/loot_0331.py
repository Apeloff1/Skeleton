"""Loot ultimate 0331.
"""
from __future__ import annotations

ID = "loot_ultimate_0331"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 331}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
