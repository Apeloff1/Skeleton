"""Ach supreme 0240.
"""
from __future__ import annotations

ID = "ach_supreme_0240"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 240}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
