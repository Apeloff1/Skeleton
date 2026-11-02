"""Econ eco_peak 0300.
"""
from __future__ import annotations

ID = "econ_eco_peak_0300"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 300}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
