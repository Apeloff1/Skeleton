"""Loot supreme 0234.
"""
from __future__ import annotations

ID = "loot_supreme_0234"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 234}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
