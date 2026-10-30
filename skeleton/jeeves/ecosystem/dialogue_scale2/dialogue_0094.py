"""Dialogue scale2 0094.
"""
from __future__ import annotations

ID = "dialogue_scale2_0094"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 94}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
