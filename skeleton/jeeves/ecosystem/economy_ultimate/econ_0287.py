"""Econ ultimate 0287.
"""
from __future__ import annotations

ID = "econ_ultimate_0287"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 287}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
