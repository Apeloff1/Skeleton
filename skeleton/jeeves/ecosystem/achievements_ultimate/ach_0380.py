"""Ach ultimate 0380.
"""
from __future__ import annotations

ID = "ach_ultimate_0380"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 380}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
