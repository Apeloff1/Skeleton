"""Loot eco_peak 0289.
"""
from __future__ import annotations

ID = "loot_eco_peak_0289"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 289}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
