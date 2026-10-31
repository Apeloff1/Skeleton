"""Loot peak 0017.
"""
from __future__ import annotations

ID = "loot_peak_0017"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
