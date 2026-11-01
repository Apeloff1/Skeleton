"""Loot ultimate 0392.
"""
from __future__ import annotations

ID = "loot_ultimate_0392"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 392}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
