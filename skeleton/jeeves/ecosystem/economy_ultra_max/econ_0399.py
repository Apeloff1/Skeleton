"""Econ ultra_max 0399.
"""
from __future__ import annotations

ID = "econ_ultra_max_0399"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 399}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
