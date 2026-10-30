"""Econ mega 0123.
"""
from __future__ import annotations

ID = "econ_mega_0123"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 123}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
