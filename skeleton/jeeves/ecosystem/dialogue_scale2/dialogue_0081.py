"""Dialogue scale2 0081.
"""
from __future__ import annotations

ID = "dialogue_scale2_0081"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 81}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
