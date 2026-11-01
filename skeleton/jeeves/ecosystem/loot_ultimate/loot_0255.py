"""Loot ultimate 0255.
"""
from __future__ import annotations

ID = "loot_ultimate_0255"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 255}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
