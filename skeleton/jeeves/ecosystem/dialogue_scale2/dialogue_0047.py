"""Dialogue scale2 0047.
"""
from __future__ import annotations

ID = "dialogue_scale2_0047"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 47}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
