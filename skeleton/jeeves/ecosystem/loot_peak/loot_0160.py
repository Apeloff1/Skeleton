"""Loot peak 0160.
"""
from __future__ import annotations

ID = "loot_peak_0160"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 160}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
