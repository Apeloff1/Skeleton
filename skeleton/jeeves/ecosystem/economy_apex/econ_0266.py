"""Econ apex 0266.
"""
from __future__ import annotations

ID = "econ_apex_0266"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 266}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
