"""Loot supreme 0360.
"""
from __future__ import annotations

ID = "loot_supreme_0360"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 360}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
