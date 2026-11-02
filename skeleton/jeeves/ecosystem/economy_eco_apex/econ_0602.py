"""Econ eco_apex 0602.
"""
from __future__ import annotations

ID = "econ_eco_apex_0602"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 602}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
