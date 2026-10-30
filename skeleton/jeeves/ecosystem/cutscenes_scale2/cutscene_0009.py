"""Cutscene scale2 0009.
"""
from __future__ import annotations

ID = "cutscene_scale2_0009"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 9}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
