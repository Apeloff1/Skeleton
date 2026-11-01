"""Loot ultimate 0417.
"""
from __future__ import annotations

ID = "loot_ultimate_0417"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 417}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
