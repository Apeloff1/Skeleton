"""Ach eco_supreme 0125.
"""
from __future__ import annotations

ID = "ach_eco_supreme_0125"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 125}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
