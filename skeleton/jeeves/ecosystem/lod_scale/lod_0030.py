"""Lod scale2 0030.
"""
from __future__ import annotations

ID = "lod_scale2_0030"

def describe() -> dict:
    return {"id": ID, "kind": "lod", "index": 30}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
