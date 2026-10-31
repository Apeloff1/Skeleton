"""Econ peak 0200.
"""
from __future__ import annotations

ID = "econ_peak_0200"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 200}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
