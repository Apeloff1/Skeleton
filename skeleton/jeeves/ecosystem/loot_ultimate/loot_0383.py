"""Loot ultimate 0383.
"""
from __future__ import annotations

ID = "loot_ultimate_0383"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 383}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
