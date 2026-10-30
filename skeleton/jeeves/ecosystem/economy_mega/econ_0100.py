"""Econ mega 0100.
"""
from __future__ import annotations

ID = "econ_mega_0100"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 100}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
