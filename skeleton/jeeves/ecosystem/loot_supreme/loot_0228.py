"""Loot supreme 0228.
"""
from __future__ import annotations

ID = "loot_supreme_0228"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 228}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
