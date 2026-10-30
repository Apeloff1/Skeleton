"""Dialogue scale2 0079.
"""
from __future__ import annotations

ID = "dialogue_scale2_0079"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 79}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
