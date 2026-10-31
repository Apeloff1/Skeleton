"""Loot peak 0193.
"""
from __future__ import annotations

ID = "loot_peak_0193"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 193}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
