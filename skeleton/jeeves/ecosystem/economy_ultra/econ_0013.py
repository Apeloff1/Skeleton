"""Econ ultra 0013.
"""
from __future__ import annotations

ID = "econ_ultra_0013"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 13}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
