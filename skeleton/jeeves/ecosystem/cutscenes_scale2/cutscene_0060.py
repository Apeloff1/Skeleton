"""Cutscene scale2 0060.
"""
from __future__ import annotations

ID = "cutscene_scale2_0060"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 60}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
