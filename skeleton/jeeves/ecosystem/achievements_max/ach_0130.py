"""Ach max 0130.
"""
from __future__ import annotations

ID = "ach_max_0130"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 130}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
