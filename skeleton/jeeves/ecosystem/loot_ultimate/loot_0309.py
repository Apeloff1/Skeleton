"""Loot ultimate 0309.
"""
from __future__ import annotations

ID = "loot_ultimate_0309"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 309}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
