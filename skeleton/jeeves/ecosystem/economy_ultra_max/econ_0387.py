"""Econ ultra_max 0387.
"""
from __future__ import annotations

ID = "econ_ultra_max_0387"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 387}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
