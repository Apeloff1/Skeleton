"""Dialogue scale2 0003.
"""
from __future__ import annotations

ID = "dialogue_scale2_0003"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 3}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
