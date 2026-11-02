"""Loot eco_supreme 0366.
"""
from __future__ import annotations

ID = "loot_eco_supreme_0366"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 366}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
