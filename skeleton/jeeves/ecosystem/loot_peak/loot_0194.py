"""Loot peak 0194.
"""
from __future__ import annotations

ID = "loot_peak_0194"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 194}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
