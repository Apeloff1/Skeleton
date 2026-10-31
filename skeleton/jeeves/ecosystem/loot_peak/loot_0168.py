"""Loot peak 0168.
"""
from __future__ import annotations

ID = "loot_peak_0168"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 168}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
