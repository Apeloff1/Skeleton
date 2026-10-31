"""Econ ultra 0120.
"""
from __future__ import annotations

ID = "econ_ultra_0120"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
