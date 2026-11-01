"""Ach ultimate 0287.
"""
from __future__ import annotations

ID = "ach_ultimate_0287"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 287}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
