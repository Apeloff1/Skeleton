"""Cutscene scale2 0025.
"""
from __future__ import annotations

ID = "cutscene_scale2_0025"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 25}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
