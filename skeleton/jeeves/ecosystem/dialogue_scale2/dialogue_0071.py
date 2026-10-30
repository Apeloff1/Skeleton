"""Dialogue scale2 0071.
"""
from __future__ import annotations

ID = "dialogue_scale2_0071"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 71}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
