"""Cull scale2 0038.
"""
from __future__ import annotations

ID = "cull_scale2_0038"

def describe() -> dict:
    return {"id": ID, "kind": "cull", "index": 38}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
