"""Loot ultimate 0261.
"""
from __future__ import annotations

ID = "loot_ultimate_0261"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 261}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
