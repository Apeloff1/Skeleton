"""Loot ultimate 0425.
"""
from __future__ import annotations

ID = "loot_ultimate_0425"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 425}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
