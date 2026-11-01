"""Loot ultimate 0350.
"""
from __future__ import annotations

ID = "loot_ultimate_0350"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 350}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
