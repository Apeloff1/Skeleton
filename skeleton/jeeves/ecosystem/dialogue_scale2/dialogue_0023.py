"""Dialogue scale2 0023.
"""
from __future__ import annotations

ID = "dialogue_scale2_0023"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 23}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
