"""Lod scale2 0048.
"""
from __future__ import annotations

ID = "lod_scale2_0048"

def describe() -> dict:
    return {"id": ID, "kind": "lod", "index": 48}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
