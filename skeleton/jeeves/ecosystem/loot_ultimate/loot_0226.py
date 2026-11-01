"""Loot ultimate 0226.
"""
from __future__ import annotations

ID = "loot_ultimate_0226"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 226}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
