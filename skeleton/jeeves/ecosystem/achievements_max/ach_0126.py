"""Ach max 0126.
"""
from __future__ import annotations

ID = "ach_max_0126"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
