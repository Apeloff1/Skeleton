"""Dialogue advanced 0085.
"""
from __future__ import annotations

ID = "dialogue_adv_0085"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 85}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
