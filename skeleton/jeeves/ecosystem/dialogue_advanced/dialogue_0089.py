"""Dialogue advanced 0089.
"""
from __future__ import annotations

ID = "dialogue_adv_0089"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 89}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
