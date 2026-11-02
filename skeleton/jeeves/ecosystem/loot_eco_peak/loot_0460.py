"""Loot eco_peak 0460.
"""
from __future__ import annotations

ID = "loot_eco_peak_0460"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 460}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
