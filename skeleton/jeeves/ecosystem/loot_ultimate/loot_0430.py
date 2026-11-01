"""Loot ultimate 0430.
"""
from __future__ import annotations

ID = "loot_ultimate_0430"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 430}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
