"""Loot eco_peak 0461.
"""
from __future__ import annotations

ID = "loot_eco_peak_0461"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 461}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
