"""Loot eco_peak 0481.
"""
from __future__ import annotations

ID = "loot_eco_peak_0481"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 481}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
