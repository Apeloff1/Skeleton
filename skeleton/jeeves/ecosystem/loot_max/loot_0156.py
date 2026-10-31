"""Loot max 0156.
"""
from __future__ import annotations

ID = "loot_max_0156"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 156}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
