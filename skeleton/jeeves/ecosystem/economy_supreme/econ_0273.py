"""Econ supreme 0273.
"""
from __future__ import annotations

ID = "econ_supreme_0273"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
