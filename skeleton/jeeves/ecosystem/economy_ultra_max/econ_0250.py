"""Econ ultra_max 0250.
"""
from __future__ import annotations

ID = "econ_ultra_max_0250"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 250}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
