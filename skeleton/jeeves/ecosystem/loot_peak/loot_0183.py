"""Loot peak 0183.
"""
from __future__ import annotations

ID = "loot_peak_0183"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 183}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
