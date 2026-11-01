"""Loot supreme 0264.
"""
from __future__ import annotations

ID = "loot_supreme_0264"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 264}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
