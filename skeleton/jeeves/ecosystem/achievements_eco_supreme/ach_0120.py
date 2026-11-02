"""Ach eco_supreme 0120.
"""
from __future__ import annotations

ID = "ach_eco_supreme_0120"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
