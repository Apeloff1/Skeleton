"""Loot ultimate 0416.
"""
from __future__ import annotations

ID = "loot_ultimate_0416"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 416}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
