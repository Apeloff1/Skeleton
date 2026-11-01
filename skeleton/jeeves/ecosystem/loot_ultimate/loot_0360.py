"""Loot ultimate 0360.
"""
from __future__ import annotations

ID = "loot_ultimate_0360"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 360}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
