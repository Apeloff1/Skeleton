"""Loot eco_peak 0473.
"""
from __future__ import annotations

ID = "loot_eco_peak_0473"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 473}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
