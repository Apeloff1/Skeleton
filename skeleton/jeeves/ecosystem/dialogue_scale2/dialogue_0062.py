"""Dialogue scale2 0062.
"""
from __future__ import annotations

ID = "dialogue_scale2_0062"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 62}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
