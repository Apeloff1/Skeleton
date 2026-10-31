"""Econ peak 0180.
"""
from __future__ import annotations

ID = "econ_peak_0180"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
