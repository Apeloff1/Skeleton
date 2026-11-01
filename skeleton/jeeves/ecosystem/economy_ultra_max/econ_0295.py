"""Econ ultra_max 0295.
"""
from __future__ import annotations

ID = "econ_ultra_max_0295"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 295}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
