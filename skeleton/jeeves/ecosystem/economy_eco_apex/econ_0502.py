"""Econ eco_apex 0502.
"""
from __future__ import annotations

ID = "econ_eco_apex_0502"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 502}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
