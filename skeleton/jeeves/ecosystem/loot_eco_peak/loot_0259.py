"""Loot eco_peak 0259.
"""
from __future__ import annotations

ID = "loot_eco_peak_0259"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 259}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
