"""Econ mega 0025.
"""
from __future__ import annotations

ID = "econ_mega_0025"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 25}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
