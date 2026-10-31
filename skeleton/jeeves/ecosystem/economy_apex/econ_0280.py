"""Econ apex 0280.
"""
from __future__ import annotations

ID = "econ_apex_0280"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 280}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
