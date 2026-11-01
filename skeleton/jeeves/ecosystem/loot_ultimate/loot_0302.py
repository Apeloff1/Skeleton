"""Loot ultimate 0302.
"""
from __future__ import annotations

ID = "loot_ultimate_0302"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 302}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
