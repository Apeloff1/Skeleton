"""Loot ultimate 0275.
"""
from __future__ import annotations

ID = "loot_ultimate_0275"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 275}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
