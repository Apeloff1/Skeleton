"""Loot peak 0173.
"""
from __future__ import annotations

ID = "loot_peak_0173"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 173}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
