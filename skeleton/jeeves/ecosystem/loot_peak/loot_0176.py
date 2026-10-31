"""Loot peak 0176.
"""
from __future__ import annotations

ID = "loot_peak_0176"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 176}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
