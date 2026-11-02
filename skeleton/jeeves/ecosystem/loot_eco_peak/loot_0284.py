"""Loot eco_peak 0284.
"""
from __future__ import annotations

ID = "loot_eco_peak_0284"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 284}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
