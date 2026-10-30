"""Dialogue scale2 0058.
"""
from __future__ import annotations

ID = "dialogue_scale2_0058"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 58}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
