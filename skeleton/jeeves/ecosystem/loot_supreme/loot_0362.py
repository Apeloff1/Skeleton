"""Loot supreme 0362.
"""
from __future__ import annotations

ID = "loot_supreme_0362"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 362}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
