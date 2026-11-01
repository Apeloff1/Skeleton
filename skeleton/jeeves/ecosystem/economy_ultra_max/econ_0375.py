"""Econ ultra_max 0375.
"""
from __future__ import annotations

ID = "econ_ultra_max_0375"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 375}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
