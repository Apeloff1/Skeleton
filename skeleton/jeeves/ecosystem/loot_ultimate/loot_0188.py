"""Loot ultimate 0188.
"""
from __future__ import annotations

ID = "loot_ultimate_0188"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 188}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
