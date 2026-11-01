"""Loot ultimate 0370.
"""
from __future__ import annotations

ID = "loot_ultimate_0370"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 370}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
