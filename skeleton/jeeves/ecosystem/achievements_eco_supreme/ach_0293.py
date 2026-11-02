"""Ach eco_supreme 0293.
"""
from __future__ import annotations

ID = "ach_eco_supreme_0293"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 293}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
